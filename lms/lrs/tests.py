"""
Comprehensive tests for LRS (Learning Record Store) implementation
Tests xAPI, cmi5, and SCORM 2004 compliance
"""

import json
import uuid
from datetime import datetime, timezone
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone as django_timezone

from .models import (
    LRS, Statement, ActivityProfile, AgentProfile, State,
    CMI5AU, CMI5Registration, CMI5Session,
    SCORM2004Sequencing, SCORM2004ActivityState
)
from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Course, Topic

User = get_user_model()


class LRSTestCase(TestCase):
    """Test case for LRS functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.lrs = LRS.objects.create(
            name='Test LRS',
            endpoint='https://lrs.example.com/xapi/',
            username='testuser',
            password='testpass',
            is_active=True
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_lrs_creation(self):
        """Test LRS creation"""
        self.assertEqual(self.lrs.name, 'Test LRS')
        self.assertTrue(self.lrs.is_active)
    
    def test_statement_creation(self):
        """Test xAPI statement creation"""
        statement_data = {
            'id': str(uuid.uuid4()),
            'actor': {
                'objectType': 'Agent',
                'name': 'Test User',
                'account': {
                    'homePage': 'https://lms.example.com/',
                    'name': str(self.user.id)
                }
            },
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/experienced',
                'display': {'en-US': 'experienced'}
            },
            'object': {
                'objectType': 'Activity',
                'id': 'https://lms.example.com/activity/123',
                'definition': {
                    'name': {'en-US': 'Test Activity'},
                    'type': 'http://adlnet.gov/expapi/activities/course'
                }
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        statement = Statement.objects.create(
            statement_id=statement_data['id'],
            actor_type='Agent',
            actor_name='Test User',
            actor_account_homepage='https://lms.example.com/',
            actor_account_name=str(self.user.id),
            verb_id=statement_data['verb']['id'],
            verb_display=statement_data['verb']['display'],
            object_type='Activity',
            object_id=statement_data['object']['id'],
            object_definition_name=statement_data['object']['definition']['name'],
            timestamp=django_timezone.now(),
            raw_statement=statement_data
        )
        
        self.assertEqual(statement.actor_name, 'Test User')
        self.assertEqual(statement.verb_id, 'http://adlnet.gov/expapi/verbs/experienced')
    
    def test_activity_profile_creation(self):
        """Test activity profile creation"""
        profile = ActivityProfile.objects.create(
            activity_id='https://lms.example.com/activity/123',
            profile_id='test-profile',
            content={'test': 'data'},
            content_type='application/json',
            etag='test-etag'
        )
        
        self.assertEqual(profile.activity_id, 'https://lms.example.com/activity/123')
        self.assertEqual(profile.profile_id, 'test-profile')
    
    def test_agent_profile_creation(self):
        """Test agent profile creation"""
        agent_data = {
            'objectType': 'Agent',
            'name': 'Test User',
            'account': {
                'homePage': 'https://lms.example.com/',
                'name': str(self.user.id)
            }
        }
        
        profile = AgentProfile.objects.create(
            agent=agent_data,
            profile_id='test-profile',
            content={'test': 'data'},
            content_type='application/json',
            etag='test-etag'
        )
        
        self.assertEqual(profile.agent['name'], 'Test User')
        self.assertEqual(profile.profile_id, 'test-profile')
    
    def test_state_creation(self):
        """Test state creation"""
        agent_data = {
            'objectType': 'Agent',
            'name': 'Test User',
            'account': {
                'homePage': 'https://lms.example.com/',
                'name': str(self.user.id)
            }
        }
        
        state = State.objects.create(
            activity_id='https://lms.example.com/activity/123',
            agent=agent_data,
            state_id='test-state',
            content={'test': 'data'},
            content_type='application/json',
            etag='test-etag'
        )
        
        self.assertEqual(state.activity_id, 'https://lms.example.com/activity/123')
        self.assertEqual(state.state_id, 'test-state')
    
    def test_cmi5_au_creation(self):
        """Test cmi5 AU creation"""
        au = CMI5AU.objects.create(
            au_id='test-au-123',
            title='Test AU',
            description='Test AU Description',
            launch_url='https://lms.example.com/launch/123',
            move_on='Completed',
            launch_method='AnyWindow'
        )
        
        self.assertEqual(au.au_id, 'test-au-123')
        self.assertEqual(au.title, 'Test AU')
        self.assertEqual(au.move_on, 'Completed')
    
    def test_cmi5_registration_creation(self):
        """Test cmi5 registration creation"""
        au = CMI5AU.objects.create(
            au_id='test-au-123',
            title='Test AU',
            launch_url='https://lms.example.com/launch/123'
        )
        
        registration = CMI5Registration.objects.create(
            au=au,
            learner=self.user,
            course_id='test-course-123',
            launch_token='test-token-123',
            launch_url='https://lms.example.com/launch/123'
        )
        
        self.assertEqual(registration.au, au)
        self.assertEqual(registration.learner, self.user)
        self.assertEqual(registration.course_id, 'test-course-123')
    
    def test_cmi5_session_creation(self):
        """Test cmi5 session creation"""
        au = CMI5AU.objects.create(
            au_id='test-au-123',
            title='Test AU',
            launch_url='https://lms.example.com/launch/123'
        )
        
        registration = CMI5Registration.objects.create(
            au=au,
            learner=self.user,
            course_id='test-course-123',
            launch_token='test-token-123',
            launch_url='https://lms.example.com/launch/123'
        )
        
        session = CMI5Session.objects.create(
            registration=registration,
            session_id=str(uuid.uuid4()),
            launch_time=django_timezone.now()
        )
        
        self.assertEqual(session.registration, registration)
        self.assertTrue(session.is_active)
    
    def test_scorm2004_sequencing_creation(self):
        """Test SCORM 2004 sequencing creation"""
        sequencing = SCORM2004Sequencing.objects.create(
            activity_id='test-activity-123',
            title='Test Activity',
            sequencing_rules={'pre_conditions': {'enabled': True}},
            rollup_rules={'completion_rollup': {'enabled': True}},
            navigation_rules={'forward_only': True},
            objectives={'obj1': {'id': 'obj1', 'description': 'Test Objective'}},
            prerequisites={'activities': []}
        )
        
        self.assertEqual(sequencing.activity_id, 'test-activity-123')
        self.assertEqual(sequencing.title, 'Test Activity')
        self.assertTrue(sequencing.sequencing_rules['pre_conditions']['enabled'])
    
    def test_scorm2004_activity_state_creation(self):
        """Test SCORM 2004 activity state creation"""
        state = SCORM2004ActivityState.objects.create(
            activity_id='test-activity-123',
            learner=self.user,
            registration_id=uuid.uuid4(),
            completion_status='incomplete',
            success_status='unknown',
            objectives={'obj1': {'id': 'obj1', 'completion_status': 'incomplete'}},
            interactions={'int1': {'id': 'int1', 'type': 'choice'}}
        )
        
        self.assertEqual(state.activity_id, 'test-activity-123')
        self.assertEqual(state.learner, self.user)
        self.assertEqual(state.completion_status, 'incomplete')


class xAPITestCase(TestCase):
    """Test case for xAPI functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.lrs = LRS.objects.create(
            name='Test LRS',
            endpoint='https://lrs.example.com/xapi/',
            username='testuser',
            password='testpass',
            is_active=True
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_statements_get(self):
        """Test GET /xapi/statements endpoint"""
        # Create test statement
        Statement.objects.create(
            statement_id=str(uuid.uuid4()),
            actor_type='Agent',
            actor_name='Test User',
            verb_id='http://adlnet.gov/expapi/verbs/experienced',
            verb_display={'en-US': 'experienced'},
            object_type='Activity',
            object_id='https://lms.example.com/activity/123',
            timestamp=django_timezone.now()
        )
        
        # Test GET request
        response = self.client.get('/lrs/xapi/statements/')
        self.assertEqual(response.status_code, 401)  # Requires authentication
    
    def test_statements_post(self):
        """Test POST /xapi/statements endpoint"""
        statement_data = {
            'id': str(uuid.uuid4()),
            'actor': {
                'objectType': 'Agent',
                'name': 'Test User',
                'account': {
                    'homePage': 'https://lms.example.com/',
                    'name': str(self.user.id)
                }
            },
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/experienced',
                'display': {'en-US': 'experienced'}
            },
            'object': {
                'objectType': 'Activity',
                'id': 'https://lms.example.com/activity/123',
                'definition': {
                    'name': {'en-US': 'Test Activity'},
                    'type': 'http://adlnet.gov/expapi/activities/course'
                }
            },
            'timestamp': django_timezone.now().isoformat(),
            'version': '1.0.3'
        }
        
        # Test POST request
        response = self.client.post(
            '/lrs/xapi/statements/',
            data=json.dumps(statement_data),
            content_type='application/json',
            HTTP_AUTHORIZATION='Basic ' + 'dGVzdHVzZXI6dGVzdHBhc3M='  # testuser:testpass
        )
        self.assertEqual(response.status_code, 200)
    
    def test_activities_get(self):
        """Test GET /xapi/activities endpoint"""
        response = self.client.get('/lrs/xapi/activities/test-activity-123/')
        self.assertEqual(response.status_code, 401)  # Requires authentication
    
    def test_activity_profiles_get(self):
        """Test GET /xapi/activities/profile endpoint"""
        response = self.client.get('/lrs/xapi/activities/test-activity-123/profile/')
        self.assertEqual(response.status_code, 401)  # Requires authentication
    
    def test_agent_profiles_get(self):
        """Test GET /xapi/agents/profile endpoint"""
        response = self.client.get('/lrs/xapi/agents/profile/')
        self.assertEqual(response.status_code, 401)  # Requires authentication
    
    def test_state_get(self):
        """Test GET /xapi/activities/state endpoint"""
        response = self.client.get('/lrs/xapi/activities/test-activity-123/state/')
        self.assertEqual(response.status_code, 401)  # Requires authentication


class CMI5TestCase(TestCase):
    """Test case for cmi5 functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.au = CMI5AU.objects.create(
            au_id='test-au-123',
            title='Test AU',
            description='Test AU Description',
            launch_url='https://lms.example.com/launch/123'
        )
        self.registration = CMI5Registration.objects.create(
            au=self.au,
            learner=self.user,
            course_id='test-course-123',
            launch_token='test-token-123',
            launch_url='https://lms.example.com/launch/123'
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_cmi5_launch_get(self):
        """Test cmi5 launch GET endpoint"""
        response = self.client.get('/lrs/cmi5/launch/?token=test-token-123')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('launch_url', data)
        self.assertIn('session_id', data)
        self.assertIn('registration_id', data)
    
    def test_cmi5_launch_invalid_token(self):
        """Test cmi5 launch with invalid token"""
        response = self.client.get('/lrs/cmi5/launch/?token=invalid-token')
        self.assertEqual(response.status_code, 404)
    
    def test_cmi5_terminate(self):
        """Test cmi5 terminate endpoint"""
        # Create session first
        session = CMI5Session.objects.create(
            registration=self.registration,
            session_id=str(uuid.uuid4()),
            launch_time=django_timezone.now()
        )
        
        data = {
            'action': 'terminate',
            'session_id': session.session_id,
            'exit_value': 'normal'
        }
        
        response = self.client.post(
            '/lrs/cmi5/launch/',
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        
        # Check session is terminated
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertIsNotNone(session.exit_time)
    
    def test_cmi5_update(self):
        """Test cmi5 update endpoint"""
        # Create session first
        session = CMI5Session.objects.create(
            registration=self.registration,
            session_id=str(uuid.uuid4()),
            launch_time=django_timezone.now()
        )
        
        data = {
            'action': 'update',
            'session_id': session.session_id,
            'session_data': {
                'raw_data': {'test': 'value'}
            }
        }
        
        response = self.client.post(
            '/lrs/cmi5/launch/',
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)


class SCORM2004TestCase(TestCase):
    """Test case for SCORM 2004 functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.sequencing = SCORM2004Sequencing.objects.create(
            activity_id='test-activity-123',
            title='Test Activity',
            sequencing_rules={'pre_conditions': {'enabled': True}},
            rollup_rules={'completion_rollup': {'enabled': True}},
            navigation_rules={'forward_only': True}
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_sequencing_get(self):
        """Test SCORM 2004 sequencing GET endpoint"""
        response = self.client.get('/lrs/scorm2004/sequencing/test-activity-123/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data['activity_id'], 'test-activity-123')
        self.assertIn('sequencing_rules', data)
        self.assertIn('rollup_rules', data)
        self.assertIn('navigation_rules', data)
    
    def test_sequencing_post(self):
        """Test SCORM 2004 sequencing POST endpoint"""
        data = {
            'title': 'Updated Activity',
            'sequencing_rules': {'pre_conditions': {'enabled': False}},
            'rollup_rules': {'completion_rollup': {'enabled': False}},
            'navigation_rules': {'forward_only': False}
        }
        
        response = self.client.post(
            '/lrs/scorm2004/sequencing/test-activity-123/',
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        
        # Check sequencing was updated
        self.sequencing.refresh_from_db()
        self.assertEqual(self.sequencing.title, 'Updated Activity')
        self.assertFalse(self.sequencing.sequencing_rules['pre_conditions']['enabled'])


class SCORMIntegrationTestCase(TestCase):
    """Test case for SCORM integration with LRS"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            description='Test Course Description'
        )
        self.topic = Topic.objects.create(
            title='Test Topic',
            description='Test Topic Description',
            content_type='SCORM'
        )
        self.scorm_package = ELearningPackage.objects.create(
            topic=self.topic,
            package_type='SCORM_1_2',
            title='Test SCORM Package',
            is_extracted=True
        )
        self.tracking = ELearningTracking.objects.create(
            user=self.user,
            elearning_package=self.scorm_package
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_scorm_api_get(self):
        """Test SCORM API GET endpoint"""
        response = self.client.get(f'/scorm/api/{self.topic.id}/?element=cmi.core.lesson_status')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('value', data)
    
    def test_scorm_api_post(self):
        """Test SCORM API POST endpoint"""
        data = {
            'action': 'SetValue',
            'element': 'cmi.core.lesson_status',
            'value': 'completed'
        }
        
        response = self.client.post(f'/scorm/api/{self.topic.id}/', data=data)
        self.assertEqual(response.status_code, 200)
        
        # Check tracking was updated
        self.tracking.refresh_from_db()
        self.assertEqual(self.tracking.completion_status, 'completed')
    
    def test_scorm_api_interactions(self):
        """Test SCORM API interactions"""
        data = {
            'action': 'SetValue',
            'element': 'cmi.interactions.0.id',
            'value': 'interaction-1'
        }
        
        response = self.client.post(f'/scorm/api/{self.topic.id}/', data=data)
        self.assertEqual(response.status_code, 200)
        
        # Check interaction was stored
        self.tracking.refresh_from_db()
        self.assertIn('0', self.tracking.interactions)
        self.assertEqual(self.tracking.interactions['0']['id'], 'interaction-1')
    
    def test_scorm_api_objectives(self):
        """Test SCORM API objectives"""
        data = {
            'action': 'SetValue',
            'element': 'cmi.objectives.0.id',
            'value': 'objective-1'
        }
        
        response = self.client.post(f'/scorm/api/{self.topic.id}/', data=data)
        self.assertEqual(response.status_code, 200)
        
        # Check objective was stored
        self.tracking.refresh_from_db()
        self.assertIn('0', self.tracking.objectives)
        self.assertEqual(self.tracking.objectives['0']['id'], 'objective-1')
    
    def test_scorm_api_comments(self):
        """Test SCORM API comments"""
        data = {
            'action': 'SetValue',
            'element': 'cmi.comments_from_learner.0.comment',
            'value': 'Test comment'
        }
        
        response = self.client.post(f'/scorm/api/{self.topic.id}/', data=data)
        self.assertEqual(response.status_code, 200)
        
        # Check comment was stored
        self.tracking.refresh_from_db()
        self.assertIn('0', self.tracking.comments_from_learner)
        self.assertEqual(self.tracking.comments_from_learner[0]['comment'], 'Test comment')
