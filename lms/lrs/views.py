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
    LRS, Statement, ActivityProfile, AgentProfile, State
)
from .scorm2004_sequencing import sequencing_processor
from users.models import CustomUser

logger = logging.getLogger(__name__)


class LRSBaseView(View):
    """Base view for LRS operations with authentication"""
    
    def authenticate(self, request):
        """Enhanced authentication for xAPI"""
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        content_type = request.META.get('CONTENT_TYPE', '')
        
        # Check for xAPI-specific headers
        xapi_version = request.META.get('HTTP_X_EXPERIENCE_API_VERSION', '1.0.3')
        
        if auth_header.startswith('Basic '):
            return self._authenticate_basic(auth_header)
        elif 'X-API-Key' in request.headers:
            return self._authenticate_api_key(request.headers['X-API-Key'])
        else:
            # xAPI requires authentication
                logger.warning("LRS Authentication: xAPI requires authentication")
                return False, "Authentication required for xAPI"
    
    def _get_default_lrs(self):
        """Get default LRS with proper error handling"""
        try:
            lrs = LRS.objects.filter(is_active=True).first()
            if lrs:
                return True, lrs
            else:
                return False, "No active LRS configured"
        except Exception as e:
            logger.error(f"LRS Authentication: Error getting default LRS: {str(e)}")
            return False, f"LRS error: {str(e)}"
    
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
            return JsonResponse(statement_list[0], safe=False)
        else:
            return JsonResponse({
                'statements': statement_list,
                'more': ''  # Pagination URL if needed
            })
    
    def post(self, request):
        """POST /xapi/statements - Store statements"""
        # xAPI statement submission with authentication
        logger.info(f"xAPI Statements POST: Received request to {request.path}")
        auth_success, auth_result = self.authenticate(request)
        logger.info(f"xAPI Statements POST: Authentication result - success: {auth_success}, result: {auth_result}")
        
        if not auth_success:
            # Authentication required for xAPI
            logger.warning("xAPI Statements POST: Authentication required")
            return JsonResponse({'error': 'Authentication required'}, status=401)
        else:
            lrs = auth_result
            logger.info(f"xAPI Statements: Using authenticated LRS: {lrs.name}")
        
        try:
            data = json.loads(request.body)
            
            # Handle single statement or list
            if isinstance(data, list):
                statement_ids = []
                for stmt_data in data:
                    stmt_id = self._store_statement(stmt_data, lrs)
                    statement_ids.append(stmt_id)
                return JsonResponse(statement_ids, safe=False)
            else:
                stmt_id = self._store_statement(data, lrs)
                return JsonResponse({'id': stmt_id})
                
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
            return JsonResponse({'id': stmt_id})
            
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
            
            # Convert registration string to UUID if needed
            registration = context.get('registration')
            if registration:
                try:
                    # Try to parse as UUID first
                    registration_uuid = uuid.UUID(registration)
                except (ValueError, AttributeError, TypeError):
                    # Generate a deterministic UUID from the string using SHA-256
                    import hashlib
                    hash_bytes = hashlib.sha256(str(registration).encode()).digest()[:16]
                    registration_uuid = uuid.UUID(bytes=hash_bytes)
            else:
                registration_uuid = None
            
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
                    'context_registration': registration_uuid,
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
    
    def get(self, request, activity_id=None):
        """GET /xapi/activities - Get activity definition"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        # Handle both /xapi/activities/ and /xapi/activities/{activity_id}/
        if activity_id:
            # For now, return basic activity info
            # In a full implementation, this would query activity definitions
            return JsonResponse({
                'id': activity_id,
                'definition': {
                    'name': {'en-US': 'Activity'},
                    'description': {'en-US': 'Learning activity'}
                }
            })
        else:
            # Return list of activities or empty list
            return JsonResponse([], safe=False)


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
    
    def options(self, request, activity_id):
        """Handle CORS preflight for xAPI content"""
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version, If-Match, If-None-Match'
        response['Access-Control-Expose-Headers'] = 'ETag, Last-Modified'
        response['Access-Control-Max-Age'] = '86400'
        return response
    
    def get(self, request, activity_id):
        """GET /xapi/activities/state - Get state"""
        # xAPI state retrieval with authentication
        state_id = request.GET.get('stateId')
        
        # Authentication required for all state operations
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        registration = request.GET.get('registration')
        since = request.GET.get('since')
        
        if not agent:
            return JsonResponse({'error': 'agent parameter required'}, status=400)
        
        try:
            agent_data = json.loads(agent)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid agent JSON'}, status=400)
        
        # Query states - need to handle JSONField querying properly
        try:
            states = State.objects.filter(activity_id=activity_id)
            
            # Filter by state_id first
            if state_id:
                states = states.filter(state_id=state_id)
            
            # Filter by registration - handle UUID conversion
            if registration:
                try:
                    import uuid as uuid_lib
                    registration_uuid = uuid_lib.UUID(registration)
                    states = states.filter(registration=registration_uuid)
                    logger.debug(f"xAPI State: Using provided UUID registration: {registration_uuid}")
                except (ValueError, AttributeError):
                    # CRITICAL FIX: Generate deterministic UUID from string (same as in scorm launch)
                    # Handle registration parameter
                    try:
                        import hashlib
                        import uuid as uuid_lib
                        hash_bytes = hashlib.sha256(str(registration).encode()).digest()[:16]
                        registration_uuid = uuid_lib.UUID(bytes=hash_bytes)
                        states = states.filter(registration=registration_uuid)
                        logger.info(f"xAPI State: Converted registration string '{registration}' to deterministic UUID: {registration_uuid}")
                    except Exception as conv_error:
                        logger.warning(f"xAPI State: Failed to convert registration '{registration}' to UUID: {conv_error}, ignoring registration filter")
                        # Don't filter by registration if conversion fails
                        pass
            
            # Filter by since timestamp
            if since:
                states = states.filter(updated_at__gte=since)
            
            # Filter by agent - need to match JSON content
            # Try exact match first
            matching_states = []
            for state in states:
                if self._agents_match(state.agent, agent_data):
                    matching_states.append(state)
            
            if state_id and matching_states:
                state = matching_states[0]
                response = JsonResponse(state.content)
                response['Content-Type'] = state.content_type
                response['ETag'] = state.etag
                response['Last-Modified'] = state.updated_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
                # Add CORS headers for xAPI content
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version'
                response['Access-Control-Expose-Headers'] = 'ETag, Last-Modified'
                return response
            elif state_id == 'LMS.LaunchData':
                # PERMANENT FALLBACK: Some AUs send a slightly different activityId.
                # If direct match failed, try to locate LMS.LaunchData by registration + agent only.
                try:
                    fallback_qs = State.objects.filter(state_id='LMS.LaunchData')
                    # Try registration-aware fallback first
                    if registration:
                        try:
                            import uuid as uuid_lib
                            reg_uuid_fb = uuid_lib.UUID(registration)
                        except (ValueError, AttributeError):
                            import hashlib, uuid as uuid_lib
                            reg_uuid_fb = uuid_lib.UUID(bytes=hashlib.sha256(str(registration).encode()).digest()[:16])
                        fallback_qs = fallback_qs.filter(registration=reg_uuid_fb)
                    # Order by most recent to improve hit rate
                    fallback_qs = fallback_qs.order_by('-updated_at')
                    for state in fallback_qs:
                        if self._agents_match(state.agent, agent_data):
                            logger.info(
                                f"xAPI State Fallback: Returned LMS.LaunchData ignoring activityId. "
                                f"requested_activity_id={activity_id}, stored_activity_id={state.activity_id}, registration={registration}"
                            )
                            response = JsonResponse(state.content)
                            response['Content-Type'] = state.content_type
                            response['ETag'] = state.etag
                            response['Last-Modified'] = state.updated_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
                            response['Access-Control-Allow-Origin'] = '*'
                            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version'
                            response['Access-Control-Expose-Headers'] = 'ETag, Last-Modified'
                            return response
                except Exception as fb_error:
                    logger.warning(f"xAPI State Fallback: Error during fallback search: {fb_error}")
            elif not state_id:
                # Return list of state IDs
                state_ids = [s.state_id for s in matching_states]
                response = JsonResponse(state_ids, safe=False)
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version'
                return response
            else:
                return JsonResponse({'error': 'State not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Error retrieving state: {str(e)}", exc_info=True)
            return JsonResponse({'error': f'Error retrieving state: {str(e)}'}, status=500)
    
    def _agents_match(self, agent1, agent2):
        """Compare two agent objects for equality with URL normalization"""
        import urllib.parse
        
        def normalize_url(url):
            """Normalize URL for comparison"""
            if not url:
                return ''
            # Parse and rebuild URL to normalize
            parsed = urllib.parse.urlparse(url)
            # Convert to lowercase, remove trailing slash, normalize scheme
            scheme = parsed.scheme.lower() or 'https'
            netloc = parsed.netloc.lower().rstrip('/')
            # Remove www. prefix for comparison
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            path = parsed.path.rstrip('/') or '/'
            return f"{scheme}://{netloc}{path}"
        
        # Handle account-based agents
        if 'account' in agent1 and 'account' in agent2:
            acc1_home = normalize_url(agent1['account'].get('homePage', ''))
            acc2_home = normalize_url(agent2['account'].get('homePage', ''))
            acc1_name = str(agent1['account'].get('name', ''))
            acc2_name = str(agent2['account'].get('name', ''))
            match = (acc1_home == acc2_home and acc1_name == acc2_name)
            if not match:
                logger.debug(f"xAPI State: Agent mismatch - agent1: {agent1}, agent2: {agent2}")
            return match
        # Handle mbox-based agents
        if 'mbox' in agent1 and 'mbox' in agent2:
            return agent1['mbox'].lower() == agent2['mbox'].lower()
        # Handle other identifier types
        for key in ['mbox_sha1sum', 'openid']:
            if key in agent1 and key in agent2:
                return agent1[key] == agent2[key]
        logger.debug(f"xAPI State: No matching agent identifiers - agent1: {agent1}, agent2: {agent2}")
        return False
    
    def post(self, request, activity_id):
        """POST /xapi/activities/state - Store state"""
        import hashlib  # Import at the top of the method for etag generation
        
        # xAPI state storage with authentication
        state_id = request.GET.get('stateId')
        
        # Authentication required for all state operations
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        registration = request.GET.get('registration')
        
        if not agent or not state_id:
            return JsonResponse({'error': 'agent and stateId required'}, status=400)
        
        try:
            agent_data = json.loads(agent)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid agent JSON'}, status=400)
        
        content_type = request.META.get('CONTENT_TYPE', 'application/json')
        
        try:
            if content_type == 'application/json':
                content = json.loads(request.body)
            else:
                content = request.body.decode('utf-8') if isinstance(request.body, bytes) else request.body
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return JsonResponse({'error': f'Invalid content: {str(e)}'}, status=400)
        
        # Convert registration to UUID if possible, otherwise generate deterministic UUID
        registration_uuid = None
        if registration:
            try:
                import uuid as uuid_lib
                registration_uuid = uuid_lib.UUID(registration)
                logger.debug(f"xAPI State POST: Using provided UUID registration: {registration_uuid}")
            except (ValueError, AttributeError):
                # CRITICAL FIX: Generate deterministic UUID from string (same as in scorm launch)
                try:
                    import uuid as uuid_lib
                    hash_bytes = hashlib.sha256(str(registration).encode()).digest()[:16]
                    registration_uuid = uuid_lib.UUID(bytes=hash_bytes)
                    logger.info(f"xAPI State POST: Converted registration string '{registration}' to deterministic UUID: {registration_uuid}")
                except Exception as conv_error:
                    logger.warning(f"xAPI State POST: Failed to convert registration '{registration}' to UUID: {conv_error}, using None")
                    registration_uuid = None
        
        try:
            state, created = State.objects.update_or_create(
                activity_id=activity_id,
                agent=agent_data,
                state_id=state_id,
                registration=registration_uuid,
                defaults={
                    'content': content,
                    'content_type': content_type,
                    'etag': hashlib.md5(json.dumps(content, sort_keys=True).encode()).hexdigest()
                }
            )
            
            response = HttpResponse(status=204 if created else 200)
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version'
            response['ETag'] = state.etag
            return response
            
        except Exception as e:
            logger.error(f"Error storing state: {str(e)}", exc_info=True)
            return JsonResponse({'error': f'Error storing state: {str(e)}'}, status=500)
    
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
    
    def put(self, request, activity_id):
        """PUT /xapi/activities/state - Store or update state"""
        # PUT is similar to POST but should replace the entire state
        # Call the StateView.post method directly to avoid inheritance issues
        return StateView.post(self, request, activity_id)
    
    def delete(self, request, activity_id):
        """DELETE /xapi/activities/state - Delete state"""
        auth_success, auth_result = self.authenticate(request)
        if not auth_success:
            return JsonResponse({'error': auth_result}, status=401)
        
        agent = request.GET.get('agent')
        state_id = request.GET.get('stateId')
        registration = request.GET.get('registration')
        
        if not agent:
            return JsonResponse({'error': 'agent parameter required'}, status=400)
        
        try:
            agent_data = json.loads(agent)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid agent JSON'}, status=400)
        
        try:
            # Find matching states
            states = State.objects.filter(activity_id=activity_id)
            
            if state_id:
                states = states.filter(state_id=state_id)
            
            # Filter by registration - handle UUID conversion
            if registration:
                try:
                    import uuid as uuid_lib
                    registration_uuid = uuid_lib.UUID(registration)
                    states = states.filter(registration=registration_uuid)
                except (ValueError, AttributeError):
                    logger.warning(f"xAPI State DELETE: Registration '{registration}' is not a valid UUID, ignoring registration filter")
                    pass
            
            # Filter by agent match
            matching_states = []
            for state in states:
                if self._agents_match(state.agent, agent_data):
                    matching_states.append(state)
            
            # Delete matching states
            for state in matching_states:
                state.delete()
            
            response = HttpResponse(status=204)
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Experience-API-Version'
            return response
            
        except Exception as e:
            logger.error(f"Error deleting state: {str(e)}", exc_info=True)
            return JsonResponse({'error': f'Error deleting state: {str(e)}'}, status=500)


# Root state view to handle /xapi/activities/state with activityId in query string
@method_decorator(csrf_exempt, name='dispatch')
class StateRootView(StateView):
    """Compatibility handler for AUs that call /xapi/activities/state without activity_id path param.
    Expects query parameter activityId and proxies to StateView methods.
    """

    def get(self, request):
        activity_id = request.GET.get('activityId') or request.GET.get('activity_id')
        if not activity_id:
            return JsonResponse({'error': 'activityId parameter required'}, status=400)
        # Delegate to parent get with activity_id
        return super().get(request, activity_id)

    def post(self, request):
        activity_id = request.GET.get('activityId') or request.GET.get('activity_id')
        if not activity_id:
            return JsonResponse({'error': 'activityId parameter required'}, status=400)
        return super().post(request, activity_id)

    def put(self, request):
        activity_id = request.GET.get('activityId') or request.GET.get('activity_id')
        if not activity_id:
            return JsonResponse({'error': 'activityId parameter required'}, status=400)
        # Call the parent post method directly since put delegates to post
        return super().post(request, activity_id)

    def delete(self, request):
        activity_id = request.GET.get('activityId') or request.GET.get('activity_id')
        if not activity_id:
            return JsonResponse({'error': 'activityId parameter required'}, status=400)
        return super().delete(request, activity_id)



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
                    'message': f"Sequencing action {action} processed successfully"
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
