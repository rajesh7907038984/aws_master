"""
xAPI Statement Generator for SCORM to xAPI conversion
Provides comprehensive SCORM 1.2, SCORM 2004, and cmi5 to xAPI statement conversion
"""

import json
import uuid
from datetime import datetime, timezone
from django.utils import timezone as django_timezone
from django.contrib.auth import get_user_model
from .models import Statement, CMI5AU, CMI5Registration

User = get_user_model()


class xAPIStatementGenerator:
    """Generate xAPI statements from SCORM data"""
    
    def __init__(self, lrs_endpoint=None):
        self.lrs_endpoint = lrs_endpoint
        self.base_actor = None
        self.base_activity = None
    
    def set_base_actor(self, user):
        """Set the base actor for statements"""
        self.base_actor = {
            "objectType": "Agent",
            "name": user.get_full_name() or user.username,
            "account": {
                "homePage": "https://lms.example.com/",
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
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"https://lms.example.com/scorm/{tracking.elearning_package.topic.id}",
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
                    'id': f"https://lms.example.com/course/{tracking.elearning_package.topic.course.id}",
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
                    'homePage': 'https://lms.example.com/',
                    'name': str(tracking.elearning_package.topic.course.instructor.id)
                }
            }
        
        statement = {
            'id': str(uuid.uuid4()),
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
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"https://lms.example.com/scorm2004/{tracking.elearning_package.topic.id}",
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
                    'id': f"https://lms.example.com/course/{tracking.elearning_package.topic.course.id}",
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
                    'homePage': 'https://lms.example.com/',
                    'name': str(tracking.elearning_package.topic.course.instructor.id)
                }
            }
        
        statement = {
            'id': str(uuid.uuid4()),
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
    
    def generate_cmi5_statement(self, registration, action, element=None, value=None):
        """Generate xAPI statement from cmi5 data"""
        if not self.base_actor:
            self.set_base_actor(registration.learner)
        
        # cmi5 specific activity
        activity = {
            "objectType": "Activity",
            "id": registration.au.au_id,
            "definition": {
                "name": {"en-US": registration.au.title},
                "description": {"en-US": registration.au.description or ""},
                "type": "http://adlnet.gov/expapi/activities/course"
            }
        }
        
        # cmi5 specific verbs
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
        
        # cmi5 specific context
        context = {
            'registration': str(registration.registration_id),
            'contextActivities': {
                'parent': [{
                    'objectType': 'Activity',
                    'id': f"https://lms.example.com/course/{registration.course_id}",
                    'definition': {
                        'name': {'en-US': f"Course {registration.course_id}"},
                        'type': 'http://adlnet.gov/expapi/activities/course'
                    }
                }]
            },
            'platform': 'LMS Platform',
            'language': 'en-US'
        }
        
        statement = {
            'id': str(uuid.uuid4()),
            'actor': self.base_actor,
            'verb': {
                'id': verb_id,
                'display': verb_display
            },
            'object': activity,
            'context': context,
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        return statement
    
    def generate_interaction_statement(self, tracking, interaction_data):
        """Generate xAPI statement for SCORM interactions"""
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"https://lms.example.com/scorm/{tracking.elearning_package.topic.id}",
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
            "id": f"https://lms.example.com/interaction/{interaction_data.get('id', 'unknown')}",
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
            'id': str(uuid.uuid4()),
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
        if not self.base_actor:
            self.set_base_actor(tracking.user)
        
        if not self.base_activity:
            self.set_base_activity(
                f"https://lms.example.com/scorm/{tracking.elearning_package.topic.id}",
                tracking.elearning_package.title or tracking.elearning_package.topic.title
            )
        
        activity = {
            "objectType": "Activity",
            "id": f"https://lms.example.com/objective/{objective_data.get('id', 'unknown')}",
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
            'id': str(uuid.uuid4()),
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
        """Store xAPI statement in the database"""
        try:
            statement = Statement.objects.create(
                statement_id=statement_data['id'],
                actor_type=statement_data['actor'].get('objectType', 'Agent'),
                actor_name=statement_data['actor'].get('name', ''),
                actor_mbox=statement_data['actor'].get('mbox', ''),
                actor_mbox_sha1sum=statement_data['actor'].get('mbox_sha1sum', ''),
                actor_openid=statement_data['actor'].get('openid', ''),
                actor_account_homepage=statement_data['actor'].get('account', {}).get('homePage', ''),
                actor_account_name=statement_data['actor'].get('account', {}).get('name', ''),
                verb_id=statement_data['verb']['id'],
                verb_display=statement_data['verb']['display'],
                object_type=statement_data['object'].get('objectType', 'Activity'),
                object_id=statement_data['object']['id'],
                object_definition_name=statement_data['object'].get('definition', {}).get('name', {}),
                object_definition_description=statement_data['object'].get('definition', {}).get('description', {}),
                object_definition_type=statement_data['object'].get('definition', {}).get('type', ''),
                result_score_scaled=statement_data.get('result', {}).get('score', {}).get('scaled'),
                result_score_raw=statement_data.get('result', {}).get('score', {}).get('raw'),
                result_score_min=statement_data.get('result', {}).get('score', {}).get('min'),
                result_score_max=statement_data.get('result', {}).get('score', {}).get('max'),
                result_success=statement_data.get('result', {}).get('success'),
                result_completion=statement_data.get('result', {}).get('completion'),
                result_response=statement_data.get('result', {}).get('response', ''),
                result_duration=statement_data.get('result', {}).get('duration'),
                context_registration=statement_data.get('context', {}).get('registration'),
                context_instructor=statement_data.get('context', {}).get('instructor', {}),
                context_team=statement_data.get('context', {}).get('team', {}),
                context_context_activities_parent=statement_data.get('context', {}).get('contextActivities', {}).get('parent', []),
                context_context_activities_grouping=statement_data.get('context', {}).get('contextActivities', {}).get('grouping', []),
                context_context_activities_category=statement_data.get('context', {}).get('contextActivities', {}).get('category', []),
                context_context_activities_other=statement_data.get('context', {}).get('contextActivities', {}).get('other', []),
                context_platform=statement_data.get('context', {}).get('platform', ''),
                context_language=statement_data.get('context', {}).get('language', ''),
                timestamp=statement_data.get('timestamp', django_timezone.now().isoformat()),
                version=statement_data.get('version', '1.0.3'),
                raw_statement=statement_data
            )
            return statement
        except Exception as e:
            print(f"Error storing statement: {str(e)}")
            return None
