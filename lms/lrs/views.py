import json
import uuid
import hashlib
import base64
from datetime import datetime, timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from django.conf import settings
import logging

from .models import (
    LRS, Statement, ActivityProfile, AgentProfile, State,
    CMI5AU, CMI5Registration, CMI5Session,
    SCORM2004Sequencing, SCORM2004ActivityState
)
from .scorm2004_sequencing import sequencing_processor
from users.models import CustomUser

logger = logging.getLogger(__name__)


class LRSBaseView(View):
    """Base view for LRS operations with authentication"""
    
    def authenticate(self, request):
        """Authenticate LRS request using Basic Auth or API Key"""
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Basic '):
            return self._authenticate_basic(auth_header)
        elif 'X-API-Key' in request.headers:
            return self._authenticate_api_key(request.headers['X-API-Key'])
        else:
            return False, "Authentication required"
    
    def _authenticate_basic(self, auth_header):
        """Authenticate using Basic Auth"""
        try:
            encoded = auth_header.split(' ')[1]
            decoded = base64.b64decode(encoded).decode('utf-8')
            username, password = decoded.split(':', 1)
            
            lrs = LRS.objects.filter(
                username=username,
                password=password,
                is_active=True
            ).first()
            
            if lrs:
                return True, lrs
            else:
                return False, "Invalid credentials"
        except Exception as e:
            return False, f"Authentication error: {str(e)}"
    
    def _authenticate_api_key(self, api_key):
        """Authenticate using API Key"""
        lrs = LRS.objects.filter(
            api_key=api_key,
            is_active=True
        ).first()
        
        if lrs:
            return True, lrs
        else:
            return False, "Invalid API key"


@method_decorator(csrf_exempt, name='dispatch')
class StatementsView(LRSBaseView):
    """xAPI Statements API endpoint"""
    
    def get(self, request):
        """GET /xapi/statements - Retrieve statements"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        lrs = auth_result
        
        # Parse query parameters
        statement_id = request.GET.get('statementId')
        voided_statement_id = request.GET.get('voidedStatementId')
        agent = request.GET.get('agent')
        verb = request.GET.get('verb')
        activity = request.GET.get('activity')
        registration = request.GET.get('registration')
        related_activities = request.GET.get('related_activities', 'false').lower() == 'true'
        related_agents = request.GET.get('related_agents', 'false').lower() == 'true'
        since = request.GET.get('since')
        until = request.GET.get('until')
        limit = int(request.GET.get('limit', 0))
        format_type = request.GET.get('format', 'exact')
        attachments = request.GET.get('attachments', 'false').lower() == 'true'
        ascending = request.GET.get('ascending', 'false').lower() == 'true'
        
        # Build query
        statements = Statement.objects.all()
        
        if statement_id:
            statements = statements.filter(statement_id=statement_id)
        if voided_statement_id:
            statements = statements.filter(statement_id=voided_statement_id)
        if agent:
            agent_data = json.loads(agent)
            statements = self._filter_by_agent(statements, agent_data)
        if verb:
            statements = statements.filter(verb_id=verb)
        if activity:
            statements = statements.filter(object_id=activity)
        if registration:
            statements = statements.filter(context_registration=registration)
        if since:
            statements = statements.filter(timestamp__gte=since)
        if until:
            statements = statements.filter(timestamp__lte=until)
        
        # Apply ordering
        if ascending:
            statements = statements.order_by('timestamp')
        else:
            statements = statements.order_by('-timestamp')
        
        # Apply limit
        if limit > 0:
            statements = statements[:limit]
        
        # Convert to xAPI format
        statement_list = []
        for stmt in statements:
            statement_data = self._statement_to_xapi(stmt)
            statement_list.append(statement_data)
        
        # Handle single statement vs list
        if statement_id and len(statement_list) == 1:
            return JsonResponse(statement_list[0])
        else:
            return JsonResponse({
                'statements': statement_list,
                'more': ''  # Pagination URL if needed
            })
    
    def post(self, request):
        """POST /xapi/statements - Store statements"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        lrs = auth_result
        
        try:
            data = json.loads(request.body)
            
            # Handle single statement or list
            if isinstance(data, list):
                statement_ids = []
                for stmt_data in data:
                    stmt_id = self._store_statement(stmt_data, lrs)
                    statement_ids.append(stmt_id)
                return JsonResponse(statement_ids)
            else:
                stmt_id = self._store_statement(data, lrs)
                return JsonResponse(stmt_id)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error storing statement: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def put(self, request):
        """PUT /xapi/statements - Store statement with specific ID"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        lrs = auth_result
        
        try:
            data = json.loads(request.body)
            statement_id = data.get('id')
            
            if not statement_id:
                return JsonResponse({'error': 'Statement ID required'}, status=400)
            
            # Check if statement already exists
            if Statement.objects.filter(statement_id=statement_id).exists():
                return JsonResponse({'error': 'Statement already exists'}, status=409)
            
            # Store the statement
            stmt_id = self._store_statement(data, lrs)
            return JsonResponse(stmt_id)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error storing statement: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def _filter_by_agent(self, queryset, agent_data):
        """Filter statements by agent"""
        if 'mbox' in agent_data:
            return queryset.filter(actor_mbox=agent_data['mbox'])
        elif 'mbox_sha1sum' in agent_data:
            return queryset.filter(actor_mbox_sha1sum=agent_data['mbox_sha1sum'])
        elif 'openid' in agent_data:
            return queryset.filter(actor_openid=agent_data['openid'])
        elif 'account' in agent_data:
            account = agent_data['account']
            return queryset.filter(
                actor_account_homepage=account['homePage'],
                actor_account_name=account['name']
            )
        return queryset.none()
    
    def _store_statement(self, stmt_data, lrs):
        """Store a statement in the database"""
        with transaction.atomic():
            # Extract actor information
            actor = stmt_data.get('actor', {})
            actor_type = actor.get('objectType', 'Agent')
            actor_mbox = actor.get('mbox', '')
            actor_mbox_sha1sum = actor.get('mbox_sha1sum', '')
            actor_openid = actor.get('openid', '')
            actor_name = actor.get('name', '')
            
            # Handle account
            actor_account = actor.get('account', {})
            actor_account_homepage = actor_account.get('homePage', '')
            actor_account_name = actor_account.get('name', '')
            
            # Extract verb information
            verb = stmt_data.get('verb', {})
            verb_id = verb.get('id', '')
            verb_display = verb.get('display', {})
            
            # Extract object information
            obj = stmt_data.get('object', {})
            object_type = obj.get('objectType', 'Activity')
            object_id = obj.get('id', '')
            object_definition = obj.get('definition', {})
            
            # Extract result information
            result = stmt_data.get('result', {})
            score = result.get('score', {})
            
            # Extract context information
            context = stmt_data.get('context', {})
            
            # Create or update statement
            statement, created = Statement.objects.update_or_create(
                statement_id=stmt_data.get('id', str(uuid.uuid4())),
                defaults={
                    'actor_type': actor_type,
                    'actor_mbox': actor_mbox,
                    'actor_mbox_sha1sum': actor_mbox_sha1sum,
                    'actor_openid': actor_openid,
                    'actor_name': actor_name,
                    'actor_account_homepage': actor_account_homepage,
                    'actor_account_name': actor_account_name,
                    'verb_id': verb_id,
                    'verb_display': verb_display,
                    'object_type': object_type,
                    'object_id': object_id,
                    'object_definition_name': object_definition.get('name', {}),
                    'object_definition_description': object_definition.get('description', {}),
                    'object_definition_type': object_definition.get('type', ''),
                    'object_definition_more_info': object_definition.get('moreInfo', ''),
                    'object_definition_interaction_type': object_definition.get('interactionType', ''),
                    'object_definition_correct_responses_pattern': object_definition.get('correctResponsesPattern', []),
                    'object_definition_choices': object_definition.get('choices', []),
                    'object_definition_scale': object_definition.get('scale', []),
                    'object_definition_source': object_definition.get('source', []),
                    'object_definition_target': object_definition.get('target', []),
                    'object_definition_steps': object_definition.get('steps', []),
                    'object_definition_extensions': object_definition.get('extensions', {}),
                    'result_score_scaled': score.get('scaled'),
                    'result_score_raw': score.get('raw'),
                    'result_score_min': score.get('min'),
                    'result_score_max': score.get('max'),
                    'result_success': result.get('success'),
                    'result_completion': result.get('completion'),
                    'result_response': result.get('response', ''),
                    'result_duration': result.get('duration'),
                    'result_extensions': result.get('extensions', {}),
                    'context_registration': context.get('registration'),
                    'context_instructor': context.get('instructor', {}),
                    'context_team': context.get('team', {}),
                    'context_context_activities_parent': context.get('contextActivities', {}).get('parent', []),
                    'context_context_activities_grouping': context.get('contextActivities', {}).get('grouping', []),
                    'context_context_activities_category': context.get('contextActivities', {}).get('category', []),
                    'context_context_activities_other': context.get('contextActivities', {}).get('other', []),
                    'context_revision': context.get('revision', ''),
                    'context_platform': context.get('platform', ''),
                    'context_language': context.get('language', ''),
                    'context_statement': context.get('statement', {}),
                    'context_extensions': context.get('extensions', {}),
                    'timestamp': stmt_data.get('timestamp', timezone.now()),
                    'authority': stmt_data.get('authority', {}),
                    'version': stmt_data.get('version', '1.0.3'),
                    'attachments': stmt_data.get('attachments', []),
                    'raw_statement': stmt_data
                }
            )
            
            return statement.statement_id
    
    def _statement_to_xapi(self, stmt):
        """Convert database statement to xAPI format"""
        return {
            'id': stmt.statement_id,
            'actor': {
                'objectType': stmt.actor_type,
                'name': stmt.actor_name,
                'mbox': stmt.actor_mbox,
                'mbox_sha1sum': stmt.actor_mbox_sha1sum,
                'openid': stmt.actor_openid,
                'account': {
                    'homePage': stmt.actor_account_homepage,
                    'name': stmt.actor_account_name
                } if stmt.actor_account_homepage else None
            },
            'verb': {
                'id': stmt.verb_id,
                'display': stmt.verb_display
            },
            'object': {
                'objectType': stmt.object_type,
                'id': stmt.object_id,
                'definition': {
                    'name': stmt.object_definition_name,
                    'description': stmt.object_definition_description,
                    'type': stmt.object_definition_type,
                    'moreInfo': stmt.object_definition_more_info,
                    'interactionType': stmt.object_definition_interaction_type,
                    'correctResponsesPattern': stmt.object_definition_correct_responses_pattern,
                    'choices': stmt.object_definition_choices,
                    'scale': stmt.object_definition_scale,
                    'source': stmt.object_definition_source,
                    'target': stmt.object_definition_target,
                    'steps': stmt.object_definition_steps,
                    'extensions': stmt.object_definition_extensions
                }
            },
            'result': {
                'score': {
                    'scaled': stmt.result_score_scaled,
                    'raw': stmt.result_score_raw,
                    'min': stmt.result_score_min,
                    'max': stmt.result_score_max
                },
                'success': stmt.result_success,
                'completion': stmt.result_completion,
                'response': stmt.result_response,
                'duration': stmt.result_duration,
                'extensions': stmt.result_extensions
            },
            'context': {
                'registration': stmt.context_registration,
                'instructor': stmt.context_instructor,
                'team': stmt.context_team,
                'contextActivities': {
                    'parent': stmt.context_context_activities_parent,
                    'grouping': stmt.context_context_activities_grouping,
                    'category': stmt.context_context_activities_category,
                    'other': stmt.context_context_activities_other
                },
                'revision': stmt.context_revision,
                'platform': stmt.context_platform,
                'language': stmt.context_language,
                'statement': stmt.context_statement,
                'extensions': stmt.context_extensions
            },
            'timestamp': stmt.timestamp.isoformat(),
            'stored': stmt.stored.isoformat(),
            'authority': stmt.authority,
            'version': stmt.version,
            'attachments': stmt.attachments
        }


@method_decorator(csrf_exempt, name='dispatch')
class ActivitiesView(LRSBaseView):
    """xAPI Activities API endpoint"""
    
    def get(self, request, activity_id):
        """GET /xapi/activities - Get activity definition"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        # For now, return basic activity info
        # In a full implementation, this would query activity definitions
        return JsonResponse({
            'id': activity_id,
            'definition': {
                'name': {'en-US': 'Activity'},
                'description': {'en-US': 'Learning activity'}
            }
        })


@method_decorator(csrf_exempt, name='dispatch')
class ActivityProfilesView(LRSBaseView):
    """xAPI Activity Profiles API endpoint"""
    
    def get(self, request, activity_id):
        """GET /xapi/activities/profile - Get activity profiles"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        profile_id = request.GET.get('profileId')
        since = request.GET.get('since')
        
        profiles = ActivityProfile.objects.filter(activity_id=activity_id)
        
        if profile_id:
            profiles = profiles.filter(profile_id=profile_id)
        if since:
            profiles = profiles.filter(updated_at__gte=since)
        
        profile_list = []
        for profile in profiles:
            profile_list.append({
                'profileId': profile.profile_id,
                'content': profile.content,
                'contentType': profile.content_type,
                'etag': profile.etag,
                'updated': profile.updated_at.isoformat()
            })
        
        return JsonResponse(profile_list, safe=False)
    
    def post(self, request, activity_id):
        """POST /xapi/activities/profile - Store activity profile"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        profile_id = request.GET.get('profileId')
        if not profile_id:
            return JsonResponse({'error': 'profileId required'}, status=400)
        
        content_type = request.META.get('CONTENT_TYPE', 'application/json')
        content = json.loads(request.body) if content_type == 'application/json' else request.body
        
        profile, created = ActivityProfile.objects.update_or_create(
            activity_id=activity_id,
            profile_id=profile_id,
            defaults={
                'content': content,
                'content_type': content_type,
                'etag': hashlib.md5(str(content).encode()).hexdigest()
            }
        )
        
        return HttpResponse(status=204 if created else 200)


@method_decorator(csrf_exempt, name='dispatch')
class AgentProfilesView(LRSBaseView):
    """xAPI Agent Profiles API endpoint"""
    
    def get(self, request):
        """GET /xapi/agents/profile - Get agent profiles"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        profile_id = request.GET.get('profileId')
        since = request.GET.get('since')
        
        if not agent:
            return JsonResponse({'error': 'agent parameter required'}, status=400)
        
        agent_data = json.loads(agent)
        profiles = AgentProfile.objects.filter(agent=agent_data)
        
        if profile_id:
            profiles = profiles.filter(profile_id=profile_id)
        if since:
            profiles = profiles.filter(updated_at__gte=since)
        
        profile_list = []
        for profile in profiles:
            profile_list.append({
                'profileId': profile.profile_id,
                'content': profile.content,
                'contentType': profile.content_type,
                'etag': profile.etag,
                'updated': profile.updated_at.isoformat()
            })
        
        return JsonResponse(profile_list, safe=False)
    
    def post(self, request):
        """POST /xapi/agents/profile - Store agent profile"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        profile_id = request.GET.get('profileId')
        
        if not agent or not profile_id:
            return JsonResponse({'error': 'agent and profileId required'}, status=400)
        
        agent_data = json.loads(agent)
        content_type = request.META.get('CONTENT_TYPE', 'application/json')
        content = json.loads(request.body) if content_type == 'application/json' else request.body
        
        profile, created = AgentProfile.objects.update_or_create(
            agent=agent_data,
            profile_id=profile_id,
            defaults={
                'content': content,
                'content_type': content_type,
                'etag': hashlib.md5(str(content).encode()).hexdigest()
            }
        )
        
        return HttpResponse(status=204 if created else 200)


@method_decorator(csrf_exempt, name='dispatch')
class StateView(LRSBaseView):
    """xAPI State API endpoint"""
    
    def get(self, request, activity_id):
        """GET /xapi/activities/state - Get state"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        state_id = request.GET.get('stateId')
        registration = request.GET.get('registration')
        since = request.GET.get('since')
        
        if not agent:
            return JsonResponse({'error': 'agent parameter required'}, status=400)
        
        agent_data = json.loads(agent)
        states = State.objects.filter(activity_id=activity_id, agent=agent_data)
        
        if state_id:
            states = states.filter(state_id=state_id)
        if registration:
            states = states.filter(registration=registration)
        if since:
            states = states.filter(updated_at__gte=since)
        
        if state_id and states.exists():
            state = states.first()
            return JsonResponse({
                'stateId': state.state_id,
                'content': state.content,
                'contentType': state.content_type,
                'etag': state.etag,
                'updated': state.updated_at.isoformat()
            })
        else:
            state_list = []
            for state in states:
                state_list.append({
                    'stateId': state.state_id,
                    'content': state.content,
                    'contentType': state.content_type,
                    'etag': state.etag,
                    'updated': state.updated_at.isoformat()
                })
            return JsonResponse(state_list, safe=False)
    
    def post(self, request, activity_id):
        """POST /xapi/activities/state - Store state"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        state_id = request.GET.get('stateId')
        registration = request.GET.get('registration')
        
        if not agent or not state_id:
            return JsonResponse({'error': 'agent and stateId required'}, status=400)
        
        agent_data = json.loads(agent)
        content_type = request.META.get('CONTENT_TYPE', 'application/json')
        content = json.loads(request.body) if content_type == 'application/json' else request.body
        
        state, created = State.objects.update_or_create(
            activity_id=activity_id,
            agent=agent_data,
            state_id=state_id,
            registration=registration,
            defaults={
                'content': content,
                'content_type': content_type,
                'etag': hashlib.md5(str(content).encode()).hexdigest()
            }
        )
        
        return HttpResponse(status=204 if created else 200)
    
    def get_resume_state(self, request, activity_id):
        """Get resume state for xAPI content"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        if not agent:
            return JsonResponse({'error': 'agent parameter required'}, status=400)
        
        agent_data = json.loads(agent)
        
        # Check for existing state that indicates resume
        states = State.objects.filter(
            activity_id=activity_id, 
            agent=agent_data
        ).order_by('-updated_at')
        
        if states.exists():
            # Check if state indicates progress/resume
            latest_state = states.first()
            state_content = latest_state.content
            
            # Determine if this is a resume scenario
            has_progress = self._check_progress_indicators(state_content)
            
            if has_progress:
                return JsonResponse({
                    'resume': True,
                    'stateId': latest_state.state_id,
                    'content': state_content,
                    'contentType': latest_state.content_type,
                    'etag': latest_state.etag,
                    'updated': latest_state.updated_at.isoformat()
                })
        
        return JsonResponse({'resume': False})

    def _check_progress_indicators(self, state_content):
        """Check if state content indicates progress for resume"""
        if isinstance(state_content, dict):
            # Check for progress indicators
            progress_indicators = [
                'completion', 'progress', 'bookmark', 'location', 
                'score', 'time_spent', 'interactions', 'suspend_data',
                'lesson_location', 'total_time', 'session_time'
            ]
            return any(indicator in str(state_content).lower() for indicator in progress_indicators)
        return False
    
    def delete(self, request, activity_id):
        """DELETE /xapi/activities/state - Delete state"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        state_id = request.GET.get('stateId')
        registration = request.GET.get('registration')
        
        if not agent or not state_id:
            return JsonResponse({'error': 'agent and stateId required'}, status=400)
        
        agent_data = json.loads(agent)
        states = State.objects.filter(
            activity_id=activity_id,
            agent=agent_data,
            state_id=state_id,
            registration=registration
        )
        
        states.delete()
        return HttpResponse(status=204)


# CMI5 specific views
@method_decorator(csrf_exempt, name='dispatch')
class CMI5LaunchView(LRSBaseView):
    """cmi5 launch endpoint"""
    
    def get(self, request):
        """Launch cmi5 AU"""
        launch_token = request.GET.get('token')
        if not launch_token:
            return JsonResponse({'error': 'Launch token required'}, status=400)
        
        try:
            registration = CMI5Registration.objects.get(
                launch_token=launch_token,
                is_active=True
            )
            
            # Create session
            session = CMI5Session.objects.create(
                registration=registration,
                session_id=str(uuid.uuid4()),
                launch_time=timezone.now()
            )
            
            # Build launch URL with parameters
            launch_url = registration.launch_url
            params = {
                'endpoint': f"{request.scheme}://{request.get_host()}/lrs/xapi/",
                'fetch': f"{request.scheme}://{request.get_host()}/lrs/xapi/activities/state",
                'actor': json.dumps({
                    'account': {
                        'homePage': f"{request.scheme}://{request.get_host()}/",
                        'name': str(registration.learner.id)
                    }
                }),
                'registration': str(registration.registration_id),
                'activityId': registration.au.au_id,
                'sessionId': session.session_id
            }
            
            # Add any additional launch parameters
            params.update(registration.launch_parameters)
            
            return JsonResponse({
                'launch_url': launch_url,
                'parameters': params
            })
            
        except CMI5Registration.DoesNotExist:
            return JsonResponse({'error': 'Invalid launch token'}, status=404)
        except Exception as e:
            logger.error(f"Error launching cmi5 AU: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)


# SCORM 2004 specific views
@method_decorator(csrf_exempt, name='dispatch')
class SCORM2004SequencingView(LRSBaseView):
    """SCORM 2004 Sequencing API with 100% compliance"""
    
    def get(self, request, activity_id):
        """Get sequencing rules for activity"""
        try:
            sequencing = SCORM2004Sequencing.objects.get(activity_id=activity_id)
            return JsonResponse({
                'activity_id': sequencing.activity_id,
                'sequencing_rules': sequencing.sequencing_rules,
                'rollup_rules': sequencing.rollup_rules,
                'navigation_rules': sequencing.navigation_rules,
                'objectives': sequencing.objectives,
                'prerequisites': sequencing.prerequisites,
                'completion_threshold': sequencing.completion_threshold,
                'mastery_score': sequencing.mastery_score
            })
        except SCORM2004Sequencing.DoesNotExist:
            return JsonResponse({'error': 'Sequencing rules not found'}, status=404)
    
    def post(self, request, activity_id):
        """Update sequencing rules with enhanced processing"""
        try:
            data = json.loads(request.body)
            
            # Process sequencing rules using the advanced processor
            sequencing, created = SCORM2004Sequencing.objects.update_or_create(
                activity_id=activity_id,
                defaults={
                    'title': data.get('title', ''),
                    'description': data.get('description', ''),
                    'sequencing_rules': data.get('sequencing_rules', {}),
                    'rollup_rules': data.get('rollup_rules', {}),
                    'navigation_rules': data.get('navigation_rules', {}),
                    'objectives': data.get('objectives', {}),
                    'prerequisites': data.get('prerequisites', {}),
                    'completion_threshold': data.get('completion_threshold'),
                    'mastery_score': data.get('mastery_score')
                }
            )
            
            # Validate sequencing rules using the processor
            if data.get('validate', False):
                validation_result = sequencing_processor.process_sequencing_rules(
                    activity_id, 
                    data.get('learner_id'), 
                    'validate', 
                    {'sequencing_rules': sequencing.sequencing_rules}
                )
                
                if validation_result.get('result') != 'true':
                    return JsonResponse({
                        'error': 'Sequencing rules validation failed',
                        'details': validation_result.get('details', {})
                    }, status=400)
            
            return JsonResponse({
                'activity_id': sequencing.activity_id,
                'created': created,
                'validation_passed': data.get('validate', False)
            })
            
        except Exception as e:
            logger.error(f"Error updating sequencing rules: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def put(self, request, activity_id):
        """Process sequencing action with full compliance"""
        try:
            data = json.loads(request.body)
            learner_id = data.get('learner_id')
            action = data.get('action', '')
            context = data.get('context', {})
            
            if not learner_id:
                return JsonResponse({'error': 'learner_id is required'}, status=400)
            
            # Process sequencing action using the advanced processor
            result = sequencing_processor.process_sequencing_rules(
                activity_id, learner_id, action, context
            )
            
            if result.get('result') == 'true':
                return JsonResponse({
                    'result': 'true',
                    'sequencing_result': result,
                    'message': f'Sequencing action {action} processed successfully'
                })
            else:
                return JsonResponse({
                    'result': 'false',
                    'error': result.get('reason', 'Sequencing processing failed'),
                    'details': result.get('details', {})
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error processing sequencing action: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
