"""
cmi5 Launch Handler
Provides complete cmi5 launch and session management
"""

import json
import uuid
import hashlib
import hmac
import time
from datetime import datetime, timezone, timedelta
from django.utils import timezone as django_timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction
import logging

from .models import CMI5AU, CMI5Registration, CMI5Session, Statement
from .xapi_generator import xAPIStatementGenerator

logger = logging.getLogger(__name__)


class CMI5LaunchHandler:
    """cmi5 Launch Handler for AU launch and session management"""
    
    def __init__(self, au_id, learner, course_id):
        self.au_id = au_id
        self.learner = learner
        self.course_id = course_id
        self.au = None
        self.registration = None
        self.session = None
        self.xapi_generator = xAPIStatementGenerator()
    
    def initialize(self):
        """Initialize cmi5 launch handler"""
        try:
            self.au = get_object_or_404(CMI5AU, au_id=self.au_id)
            self.registration, created = CMI5Registration.objects.get_or_create(
                au=self.au,
                learner=self.learner,
                course_id=self.course_id,
                defaults={
                    'launch_token': self._generate_launch_token(),
                    'launch_url': self.au.launch_url,
                    'launch_parameters': self.au.launch_parameters
                }
            )
            return True
        except Exception as e:
            logger.error("Error initializing cmi5 launch handler: {{str(e)}}")
            return False
    
    def _generate_launch_token(self):
        """Generate secure launch token"""
        timestamp = str(int(time.time()))
        data = "{{self.au_id}}:{{self.learner.id}}:{{self.course_id}}:{{timestamp}}"
        token = hashlib.sha256(data.encode()).hexdigest()
        return token
    
    def launch_au(self, launch_url=None, launch_parameters=None):
        """Launch cmi5 AU"""
        if not self.initialize():
            return None, "Failed to initialize launch handler"
        
        try:
            # Check for resume state first
            resume_state = self.check_resume_state()
            
            # Create new session
            self.session = CMI5Session.objects.create(
                registration=self.registration,
                session_id=str(uuid.uuid4()),
                launch_time=django_timezone.now()
            )
            
            # Generate launch URL with parameters
            launch_url = launch_url or self.au.launch_url
            launch_params = launch_parameters or self.au.launch_parameters.copy()
            
            # Add cmi5 required parameters
            launch_params.update({
                'endpoint': "{{settings.LRS_ENDPOINT}}/xapi/statements/",
                'fetch': "{{settings.LRS_ENDPOINT}}/xapi/activities/state",
                'actor': json.dumps({
                    'account': {
                        'homePage': "{{settings.LMS_BASE_URL}}/",
                        'name': str(self.learner.id)
                    }
                }),
                'registration': str(self.registration.registration_id),
                'activityId': self.au.au_id,
                'sessionId': self.session.session_id
            })
            
            # Add resume state if available
            if resume_state.get('resume'):
                launch_params.update({
                    'resume': 'true',
                    'resumeState': json.dumps(resume_state.get('state', {}))
                })
                logger.info("cmi5: Launching with resume state for AU {{self.au.au_id}}")
            else:
                launch_params.update({
                    'resume': 'false'
                })
                logger.info("cmi5: Launching fresh for AU {{self.au.au_id}}")
            
            # Generate launch URL with parameters
            launch_url_with_params = self._build_launch_url(launch_url, launch_params)
            
            # Generate launched statement
            statement = self._generate_launched_statement()
            if statement:
                self._store_statement(statement)
            
            return {
                'launch_url': launch_url_with_params,
                'session_id': self.session.session_id,
                'registration_id': str(self.registration.registration_id)
            }, None
            
        except Exception as e:
            logger.error("Error launching cmi5 AU: {{str(e)}}")
            return None, str(e)
    
    def _build_launch_url(self, base_url, parameters):
        """Build launch URL with parameters"""
        import urllib.parse
        
        # Add parameters to URL
        if '?' in base_url:
            separator = '&'
        else:
            separator = '?'
        
        param_string = urllib.parse.urlencode(parameters)
        return "{{base_url}}{{separator}}{{param_string}}"
    
    def _generate_launched_statement(self):
        """Generate cmi5 launched statement"""
        self.xapi_generator.set_base_actor(self.learner)
        
        activity = {
            "objectType": "Activity",
            "id": self.au.au_id,
            "definition": {
                "name": {"en-US": self.au.title},
                "description": {"en-US": self.au.description or ""},
                "type": "http://adlnet.gov/expapi/activities/course"
            }
        }
        
        statement = {
            'id': str(uuid.uuid4()),
            'actor': self.xapi_generator.base_actor,
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/launched',
                'display': {'en-US': 'launched'}
            },
            'object': activity,
            'context': {
                'registration': str(self.registration.registration_id),
                'contextActivities': {
                    'parent': [{
                        'objectType': 'Activity',
                        'id': "https://lms.example.com/course/{{self.course_id}}",
                        'definition': {
                            'name': {'en-US': "Course {{self.course_id}}"},
                            'type': 'http://adlnet.gov/expapi/activities/course'
                        }
                    }]
                },
                'platform': 'LMS Platform',
                'language': 'en-US'
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def terminate_session(self, exit_value='normal'):
        """Terminate cmi5 session"""
        if not self.session:
            return False, "No active session"
        
        try:
            with transaction.atomic():
                # Update session
                self.session.exit_time = django_timezone.now()
                self.session.is_active = False
                self.session.session_time = self.session.exit_time - self.session.launch_time
                self.session.save()
                
                # Generate terminated statement
                statement = self._generate_terminated_statement(exit_value)
                if statement:
                    self._store_statement(statement)
                
                return True, "Session terminated"
                
        except Exception as e:
            logger.error("Error terminating cmi5 session: {{str(e)}}")
            return False, str(e)
    
    def _generate_terminated_statement(self, exit_value):
        """Generate cmi5 terminated statement"""
        self.xapi_generator.set_base_actor(self.learner)
        
        activity = {
            "objectType": "Activity",
            "id": self.au.au_id,
            "definition": {
                "name": {"en-US": self.au.title},
                "description": {"en-US": self.au.description or ""},
                "type": "http://adlnet.gov/expapi/activities/course"
            }
        }
        
        statement = {
            'id': str(uuid.uuid4()),
            'actor': self.xapi_generator.base_actor,
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/terminated',
                'display': {'en-US': 'terminated'}
            },
            'object': activity,
            'result': {
                'extensions': {
                    'http://adlnet.gov/expapi/result/exit': exit_value
                }
            },
            'context': {
                'registration': str(self.registration.registration_id),
                'contextActivities': {
                    'parent': [{
                        'objectType': 'Activity',
                        'id': "https://lms.example.com/course/{{self.course_id}}",
                        'definition': {
                            'name': {'en-US': "Course {{self.course_id}}"},
                            'type': 'http://adlnet.gov/expapi/activities/course'
                        }
                    }]
                },
                'platform': 'LMS Platform',
                'language': 'en-US'
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def check_resume_state(self):
        """Check if AU should resume from previous state"""
        try:
            # Check for existing session with progress
            previous_sessions = CMI5Session.objects.filter(
                registration=self.registration
            ).order_by('-launch_time')
            
            if previous_sessions.exists():
                last_session = previous_sessions.first()
                
                # Check for progress indicators
                has_progress = self._check_cmi5_progress(last_session)
                
                if has_progress:
                    # Get state from xAPI
                    state_data = self._get_activity_state()
                    return {
                        'resume': True,
                        'state': state_data,
                        'session_id': last_session.session_id,
                        'previous_session': last_session
                    }
            
            return {'resume': False}
            
        except Exception as e:
            logger.error("Error checking cmi5 resume state: {{str(e)}}")
            return {'resume': False}

    def _check_cmi5_progress(self, session):
        """Check if cmi5 session has progress indicators"""
        # Check for completion, score, time spent, etc.
        return (
            session.completion_status == 'completed' or
            session.score_raw is not None or
            (session.total_time and session.total_time.total_seconds() > 0) or
            bool(session.suspend_data) or
            bool(session.location)
        )

    def _get_activity_state(self):
        """Get activity state from xAPI for resume"""
        try:
            # Query xAPI state API for resume data
            from django.test import Client
            from django.urls import reverse
            
            # Create a test client to query xAPI state
            client = Client()
            
            # Build agent data for xAPI query
            agent_data = {
                'account': {
                    'homePage': "{{settings.LMS_BASE_URL}}/",
                    'name': str(self.learner.id)
                }
            }
            
            # Query state API
            state_url = "/lrs/xapi/activities/{{self.au.au_id}}/state/"
            response = client.get(state_url, {
                'agent': json.dumps(agent_data)
            })
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning("Failed to get cmi5 activity state: {{response.status_code}}")
                return None
                
        except Exception as e:
            logger.error("Error getting cmi5 activity state: {{str(e)}}")
            return None
    
    def _store_statement(self, statement_data):
        """Store xAPI statement"""
        try:
            self.xapi_generator.store_statement(statement_data)
        except Exception as e:
            logger.error("Error storing statement: {{str(e)}}")
    
    def get_session_state(self):
        """Get current session state"""
        if not self.session:
            return None
        
        return {
            'session_id': self.session.session_id,
            'registration_id': str(self.registration.registration_id),
            'au_id': self.au.au_id,
            'launch_time': self.session.launch_time.isoformat(),
            'exit_time': self.session.exit_time.isoformat() if self.session.exit_time else None,
            'session_time': str(self.session.session_time) if self.session.session_time else None,
            'is_active': self.session.is_active
        }
    
    def update_session(self, session_data):
        """Update session with new data"""
        if not self.session:
            return False, "No active session"
        
        try:
            with transaction.atomic():
                # Update session time
                if 'session_time' in session_data:
                    self.session.session_time = session_data['session_time']
                
                # Update raw data
                if 'raw_data' in session_data:
                    self.session.raw_data = session_data['raw_data']
                
                self.session.save()
                
                return True, "Session updated"
                
        except Exception as e:
            logger.error("Error updating session: {{str(e)}}")
            return False, str(e)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cmi5_launch_endpoint(request):
    """cmi5 launch endpoint"""
    if request.method == 'GET':
        return _handle_cmi5_launch_get(request)
    elif request.method == 'POST':
        return _handle_cmi5_launch_post(request)


def _handle_cmi5_launch_get(request):
    """Handle cmi5 launch GET request"""
    launch_token = request.GET.get('token')
    if not launch_token:
        return JsonResponse({'error': 'Launch token required'}, status=400)
    
    try:
        registration = CMI5Registration.objects.get(
            launch_token=launch_token,
            is_active=True
        )
        
        handler = CMI5LaunchHandler(
            registration.au.au_id,
            registration.learner,
            registration.course_id
        )
        
        launch_data, error = handler.launch_au()
        if error:
            return JsonResponse({'error': error}, status=500)
        
        return JsonResponse(launch_data)
        
    except CMI5Registration.DoesNotExist:
        return JsonResponse({'error': 'Invalid launch token'}, status=404)
    except Exception as e:
        logger.error("Error in cmi5 launch: {{str(e)}}")
        return JsonResponse({'error': str(e)}, status=500)


def _handle_cmi5_launch_post(request):
    """Handle cmi5 launch POST request"""
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'terminate':
            return _handle_cmi5_terminate(request, data)
        elif action == 'update':
            return _handle_cmi5_update(request, data)
        else:
            return JsonResponse({'error': 'Unknown action'}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error("Error in cmi5 launch POST: {{str(e)}}")
        return JsonResponse({'error': str(e)}, status=500)


def _handle_cmi5_terminate(request, data):
    """Handle cmi5 terminate request"""
    session_id = data.get('session_id')
    exit_value = data.get('exit_value', 'normal')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID required'}, status=400)
    
    try:
        session = CMI5Session.objects.get(
            session_id=session_id,
            is_active=True
        )
        
        handler = CMI5LaunchHandler(
            session.registration.au.au_id,
            session.registration.learner,
            session.registration.course_id
        )
        handler.session = session
        
        success, error = handler.terminate_session(exit_value)
        if not success:
            return JsonResponse({'error': error}, status=500)
        
        return JsonResponse({'status': 'terminated'})
        
    except CMI5Session.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error("Error terminating cmi5 session: {{str(e)}}")
        return JsonResponse({'error': str(e)}, status=500)


def _handle_cmi5_update(request, data):
    """Handle cmi5 update request"""
    session_id = data.get('session_id')
    session_data = data.get('session_data', {})
    
    if not session_id:
        return JsonResponse({'error': 'Session ID required'}, status=400)
    
    try:
        session = CMI5Session.objects.get(
            session_id=session_id,
            is_active=True
        )
        
        handler = CMI5LaunchHandler(
            session.registration.au.au_id,
            session.registration.learner,
            session.registration.course_id
        )
        handler.session = session
        
        success, error = handler.update_session(session_data)
        if not success:
            return JsonResponse({'error': error}, status=500)
        
        return JsonResponse({'status': 'updated'})
        
    except CMI5Session.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error("Error updating cmi5 session: {{str(e)}}")
        return JsonResponse({'error': str(e)}, status=500)
