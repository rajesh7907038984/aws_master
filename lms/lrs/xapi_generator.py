"""
xAPI Statement Generator for SCORM to xAPI conversion
Provides comprehensive SCORM 1.2, SCORM 2004, and xAPI statement conversion
"""

import json
import uuid
from datetime import datetime, timezone
from django.utils import timezone as django_timezone
from django.contrib.auth import get_user_model
from .models import Statement

User = get_user_model()


class xAPIStatementGenerator:
    """Generate xAPI statements from SCORM data"""
    
    def __init__(self, lrs_endpoint=None):
        self.lrs_endpoint = lrs_endpoint
        self.base_actor = None
        self.base_activity = None
    
    def set_base_actor(self, user):
        """Set the base actor for statements"""
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', 'https://lms.example.com')
        self.base_actor = {
            "objectType": "Agent",
            "name": user.get_full_name() or user.username,
            "account": {
                "homePage": f"{site_url}/",
                "name": str(user.id)
            }
        }
    
    def set_base_activity(self, activity_id, activity_name):
        """Set the base activity for statements"""
        self.base_activity = {
            "objectType": "Activity",
            "id": activity_id,
            "definition": {
                "name": {"en-US": activity_name},
                "type": "http://adlnet.gov/expapi/activities/course"
            }
        }
    
    def generate_scorm_1_2_statement(self, tracking, action, element=None, value=None):
        """Generate xAPI statement from SCORM 1.2 data"""
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', 'https://lms.example.com')
        
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"{site_url}/scorm/{tracking.elearning_package.topic.id}",
                tracking.elearning_package.title or tracking.elearning_package.topic.title
            )
        
        # Map SCORM 1.2 actions to xAPI verbs
        verb_mapping = {
            'launched': 'http://adlnet.gov/expapi/verbs/launched',
            'initialized': 'http://adlnet.gov/expapi/verbs/initialized',
            'completed': 'http://adlnet.gov/expapi/verbs/completed',
            'passed': 'http://adlnet.gov/expapi/verbs/passed',
            'failed': 'http://adlnet.gov/expapi/verbs/failed',
            'suspended': 'http://adlnet.gov/expapi/verbs/suspended',
            'resumed': 'http://adlnet.gov/expapi/verbs/resumed',
            'terminated': 'http://adlnet.gov/expapi/verbs/terminated',
            'progressed': 'http://adlnet.gov/expapi/verbs/progressed',
            'answered': 'http://adlnet.gov/expapi/verbs/answered',
            'interacted': 'http://adlnet.gov/expapi/verbs/interacted'
        }
        
        verb_id = verb_mapping.get(action, 'http://adlnet.gov/expapi/verbs/experienced')
        verb_display = {
            "en-US": action.replace('_', ' ').title()
        }
        
        # Build result object
        result = {}
        if tracking.completion_status:
            result['completion'] = tracking.completion_status == 'completed'
        if tracking.success_status:
            result['success'] = tracking.success_status == 'passed'
        if tracking.score_raw is not None:
            result['score'] = {
                'raw': tracking.score_raw,
                'min': tracking.score_min or 0,
                'max': tracking.score_max or 100,
                'scaled': tracking.score_scaled or (tracking.score_raw / tracking.score_max if tracking.score_max else 0)
            }
        if tracking.progress_measure is not None:
            result['extensions'] = {
                'http://adlnet.gov/expapi/result/progress': tracking.progress_measure
            }
        
        # Build context
        context = {
            'registration': str(tracking.registration_id),
            'contextActivities': {
                'parent': [{
                    'objectType': 'Activity',
                    'id': f"{site_url}/course/{tracking.elearning_package.topic.course.id}",
                    'definition': {
                        'name': {'en-US': tracking.elearning_package.topic.course.title},
                        'type': 'http://adlnet.gov/expapi/activities/course'
                    }
                }]
            },
            'platform': 'LMS Platform',
            'language': 'en-US'
        }
        
        # Add instructor if available
        if hasattr(tracking.elearning_package.topic.course, 'instructor'):
            context['instructor'] = {
                'objectType': 'Agent',
                'name': tracking.elearning_package.topic.course.instructor.get_full_name(),
                'account': {
                    'homePage': f"{site_url}/",
                    'name': str(tracking.elearning_package.topic.course.instructor.id)
                }
            }
        
        statement = {
            'id': str(uuid.uuid4()),  # FIXED: Proper UUID format
            'actor': self.base_actor,
            'verb': {
                'id': verb_id,
                'display': verb_display
            },
            'object': self.base_activity,
            'result': result if result else None,
            'context': context,
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def generate_scorm_2004_statement(self, tracking, action, element=None, value=None):
        """Generate xAPI statement from SCORM 2004 data"""
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', 'https://lms.example.com')
        
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"{site_url}/scorm2004/{tracking.elearning_package.topic.id}",
                tracking.elearning_package.title or tracking.elearning_package.topic.title
            )
        
        # Enhanced verb mapping for SCORM 2004
        verb_mapping = {
            'launched': 'http://adlnet.gov/expapi/verbs/launched',
            'initialized': 'http://adlnet.gov/expapi/verbs/initialized',
            'completed': 'http://adlnet.gov/expapi/verbs/completed',
            'passed': 'http://adlnet.gov/expapi/verbs/passed',
            'failed': 'http://adlnet.gov/expapi/verbs/failed',
            'suspended': 'http://adlnet.gov/expapi/verbs/suspended',
            'resumed': 'http://adlnet.gov/expapi/verbs/resumed',
            'terminated': 'http://adlnet.gov/expapi/verbs/terminated',
            'progressed': 'http://adlnet.gov/expapi/verbs/progressed',
            'answered': 'http://adlnet.gov/expapi/verbs/answered',
            'interacted': 'http://adlnet.gov/expapi/verbs/interacted',
            'mastered': 'http://adlnet.gov/expapi/verbs/mastered',
            'experienced': 'http://adlnet.gov/expapi/verbs/experienced'
        }
        
        verb_id = verb_mapping.get(action, 'http://adlnet.gov/expapi/verbs/experienced')
        verb_display = {
            "en-US": action.replace('_', ' ').title()
        }
        
        # Enhanced result object for SCORM 2004
        result = {}
        if tracking.completion_status:
            result['completion'] = tracking.completion_status == 'completed'
        if tracking.success_status:
            result['success'] = tracking.success_status == 'passed'
        if tracking.score_raw is not None:
            result['score'] = {
                'raw': tracking.score_raw,
                'min': tracking.score_min or 0,
                'max': tracking.score_max or 100,
                'scaled': tracking.score_scaled or (tracking.score_raw / tracking.score_max if tracking.score_max else 0)
            }
        if tracking.progress_measure is not None:
            result['extensions'] = {
                'http://adlnet.gov/expapi/result/progress': tracking.progress_measure
            }
        
        # Add duration if available
        if tracking.session_time:
            result['duration'] = str(tracking.session_time)
        
        # Enhanced context for SCORM 2004
        context = {
            'registration': str(tracking.registration_id),
            'contextActivities': {
                'parent': [{
                    'objectType': 'Activity',
                    'id': f"{site_url}/course/{tracking.elearning_package.topic.course.id}",
                    'definition': {
                        'name': {'en-US': tracking.elearning_package.topic.course.title},
                        'type': 'http://adlnet.gov/expapi/activities/course'
                    }
                }]
            },
            'platform': 'LMS Platform',
            'language': 'en-US'
        }
        
        # Add objectives if available
        if tracking.objectives:
            context['contextActivities']['category'] = [{
                'objectType': 'Activity',
                'id': 'http://adlnet.gov/expapi/activities/objective',
                'definition': {
                    'name': {'en-US': 'Learning Objectives'},
                    'type': 'http://adlnet.gov/expapi/activities/objective'
                }
            }]
        
        # Add instructor if available
        if hasattr(tracking.elearning_package.topic.course, 'instructor'):
            context['instructor'] = {
                'objectType': 'Agent',
                'name': tracking.elearning_package.topic.course.instructor.get_full_name(),
                'account': {
                    'homePage': f"{site_url}/",
                    'name': str(tracking.elearning_package.topic.course.instructor.id)
                }
            }
        
        statement = {
            'id': str(uuid.uuid4()),  # FIXED: Proper UUID format
            'actor': self.base_actor,
            'verb': {
                'id': verb_id,
                'display': verb_display
            },
            'object': self.base_activity,
            'result': result if result else None,
            'context': context,
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    
    def generate_interaction_statement(self, tracking, interaction_data):
        """Generate xAPI statement for SCORM interactions"""
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', 'https://lms.example.com')
        
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"{site_url}/scorm/{tracking.elearning_package.topic.id}",
                tracking.elearning_package.title or tracking.elearning_package.topic.title
            )
        
        # Map interaction type to xAPI activity type
        interaction_type_mapping = {
            'choice': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'fill-in': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'matching': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'performance': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'sequencing': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'likert': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'numeric': 'http://adlnet.gov/expapi/activities/cmi.interaction',
            'other': 'http://adlnet.gov/expapi/activities/cmi.interaction'
        }
        
        activity = {
            "objectType": "Activity",
            "id": f"{site_url}/interaction/{interaction_data.get('id', 'unknown')}",
            "definition": {
                "name": {"en-US": interaction_data.get('description', 'Interaction')},
                "type": interaction_type_mapping.get(
                    interaction_data.get('type', 'other'),
                    'http://adlnet.gov/expapi/activities/cmi.interaction'
                ),
                "interactionType": interaction_data.get('type', 'other'),
                "correctResponsesPattern": interaction_data.get('correct_responses', []),
                "choices": interaction_data.get('choices', []),
                "scale": interaction_data.get('scale', []),
                "source": interaction_data.get('source', []),
                "target": interaction_data.get('target', []),
                "steps": interaction_data.get('steps', [])
            }
        }
        
        # Build result
        result = {}
        if interaction_data.get('result'):
            result['success'] = interaction_data['result'] == 'correct'
        if interaction_data.get('learner_response'):
            result['response'] = interaction_data['learner_response']
        if interaction_data.get('latency'):
            result['duration'] = f"PT{interaction_data['latency']}S"
        
        statement = {
            'id': str(uuid.uuid4()),  # FIXED: Proper UUID format
            'actor': self.base_actor,
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/answered',
                'display': {'en-US': 'answered'}
            },
            'object': activity,
            'result': result if result else None,
            'context': {
                'registration': str(tracking.registration_id),
                'contextActivities': {
                    'parent': [self.base_activity]
                }
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def generate_objective_statement(self, tracking, objective_data):
        """Generate xAPI statement for SCORM objectives"""
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', 'https://lms.example.com')
        
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"{site_url}/scorm/{tracking.elearning_package.topic.id}",
                tracking.elearning_package.title or tracking.elearning_package.topic.title
            )
        
        activity = {
            "objectType": "Activity",
            "id": f"{site_url}/objective/{objective_data.get('id', 'unknown')}",
            "definition": {
                "name": {"en-US": objective_data.get('description', 'Learning Objective')},
                "type": "http://adlnet.gov/expapi/activities/objective"
            }
        }
        
        # Determine verb based on objective status
        if objective_data.get('completion_status') == 'completed':
            verb_id = 'http://adlnet.gov/expapi/verbs/completed'
            verb_display = {'en-US': 'completed'}
        elif objective_data.get('success_status') == 'passed':
            verb_id = 'http://adlnet.gov/expapi/verbs/passed'
            verb_display = {'en-US': 'passed'}
        else:
            verb_id = 'http://adlnet.gov/expapi/verbs/experienced'
            verb_display = {'en-US': 'experienced'}
        
        # Build result
        result = {}
        if objective_data.get('completion_status'):
            result['completion'] = objective_data['completion_status'] == 'completed'
        if objective_data.get('success_status'):
            result['success'] = objective_data['success_status'] == 'passed'
        if objective_data.get('score'):
            result['score'] = objective_data['score']
        if objective_data.get('progress_measure'):
            result['extensions'] = {
                'http://adlnet.gov/expapi/result/progress': objective_data['progress_measure']
            }
        
        statement = {
            'id': str(uuid.uuid4()),  # FIXED: Proper UUID format
            'actor': self.base_actor,
            'verb': {
                'id': verb_id,
                'display': verb_display
            },
            'object': activity,
            'result': result if result else None,
            'context': {
                'registration': str(tracking.registration_id),
                'contextActivities': {
                    'parent': [self.base_activity]
                }
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def store_statement(self, statement_data, lrs=None):
        """Enhanced xAPI statement storage with comprehensive error handling"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Enhanced validation before storage
            if not self._validate_statement_structure(statement_data):
                logger.error("xAPI Statement: Invalid structure")
                return None
            
            # Extract nested values with enhanced error handling
            actor = statement_data.get('actor', {})
            verb = statement_data.get('verb', {})
            obj = statement_data.get('object', {})
            result = statement_data.get('result', {})
            context = statement_data.get('context', {})
            
            # Enhanced actor account extraction
            actor_account = actor.get('account', {})
            
            # Create statement with enhanced error handling
            statement = Statement.objects.create(
                statement_id=statement_data.get('id', str(uuid.uuid4())),
                lrs=lrs,  # FIXED: Associate with LRS
                actor_type=actor.get('objectType', 'Agent'),
                actor_name=actor.get('name', ''),
                actor_mbox=actor.get('mbox', ''),
                actor_mbox_sha1sum=actor.get('mbox_sha1sum', ''),
                actor_openid=actor.get('openid', ''),
                actor_account_homepage=actor_account.get('homePage', ''),
                actor_account_name=actor_account.get('name', ''),
                verb_id=verb.get('id', ''),
                verb_display=verb.get('display', {}),
                object_type=obj.get('objectType', 'Activity'),
                object_id=obj.get('id', ''),
                object_definition_name=obj.get('definition', {}).get('name', {}),
                object_definition_description=obj.get('definition', {}).get('description', {}),
                object_definition_type=obj.get('definition', {}).get('type', ''),
                result_score_scaled=result.get('score', {}).get('scaled'),
                result_score_raw=result.get('score', {}).get('raw'),
                result_score_min=result.get('score', {}).get('min'),
                result_score_max=result.get('score', {}).get('max'),
                result_success=result.get('success'),
                result_completion=result.get('completion'),
                result_response=result.get('response', ''),
                result_duration=result.get('duration'),
                context_registration=context.get('registration'),
                context_instructor=context.get('instructor', {}),
                context_team=context.get('team', {}),
                context_context_activities_parent=context.get('contextActivities', {}).get('parent', []),
                context_context_activities_grouping=context.get('contextActivities', {}).get('grouping', []),
                context_context_activities_category=context.get('contextActivities', {}).get('category', []),
                context_context_activities_other=context.get('contextActivities', {}).get('other', []),
                context_platform=context.get('platform', ''),
                context_language=context.get('language', ''),
                timestamp=statement_data.get('timestamp', django_timezone.now().isoformat()),
                version=statement_data.get('version', '1.0.3'),
                raw_statement=statement_data,
                stored_at=django_timezone.now()
            )
            
            logger.info(f"xAPI Statement Stored Successfully: {statement.statement_id}")
            return statement
            
        except Exception as e:
            logger.error(f"xAPI Statement Storage Error: {str(e)}", exc_info=True)
            return None
    
    def _validate_statement_structure(self, statement_data):
        """Enhanced statement structure validation"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Check required fields
            required_fields = ['id', 'actor', 'verb', 'object', 'timestamp']
            for field in required_fields:
                if field not in statement_data:
                    logger.error(f"xAPI Statement: Missing required field '{field}'")
                    return False
            
            # Validate actor structure
            actor = statement_data.get('actor', {})
            if not actor.get('objectType'):
                logger.error("xAPI Statement: Actor missing objectType")
                return False
            
            # Validate verb structure
            verb = statement_data.get('verb', {})
            if not verb.get('id'):
                logger.error("xAPI Statement: Verb missing id")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"xAPI Statement Validation Error: {str(e)}")
            return False
