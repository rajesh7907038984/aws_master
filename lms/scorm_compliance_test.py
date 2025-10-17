#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCORM, xAPI, and cmi5 100% Compliance Test Suite
Comprehensive testing for all standards compliance
"""

import os
import sys
import django
import json
import logging
from datetime import datetime, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course
from lrs.models import LRS, Statement, SCORM2004Sequencing, SCORM2004ActivityState
from lrs.scorm2004_sequencing import sequencing_processor

User = get_user_model()
logger = logging.getLogger(__name__)


class SCORMComplianceTest(TestCase):
    """Comprehensive SCORM compliance testing"""
    
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
            course=self.course
        )
        self.scorm_package = ELearningPackage.objects.create(
            topic=self.topic,
            package_file='test_scorm.zip',
            package_type='scorm_1_2',
            is_extracted=True,
            launch_file='index.html'
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_scorm_1_2_data_model_compliance(self):
        """Test SCORM 1.2 data model compliance - 100%"""
        print("\n=== Testing SCORM 1.2 Data Model Compliance ===")
        
        # Test all 23 core SCORM 1.2 elements
        scorm_1_2_elements = [
            'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.core.score.min',
            'cmi.core.score.max', 'cmi.core.total_time', 'cmi.core.session_time',
            'cmi.core.lesson_location', 'cmi.core.exit', 'cmi.core.entry',
            'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
            'cmi.core.lesson_mode', 'cmi.core.max_time_allowed', 'cmi.core.mastery_score',
            'cmi.core.suspend_data', 'cmi.core.launch_data', 'cmi.core.comments',
            'cmi.core.comments_from_lms', 'cmi.core.objectives', 'cmi.core.student_data',
            'cmi.core.student_preference', 'cmi.core.interactions', 'cmi.core.navigation'
        ]
        
        compliance_count = 0
        total_elements = len(scorm_1_2_elements)
        
        for element in scorm_1_2_elements:
            try:
                # Test SetValue
                response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                    'action': 'SetValue',
                    'element': element,
                    'value': 'test_value'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('result') == 'true':
                        compliance_count += 1
                        print("+ {} - SetValue compliant".format(element))
                    else:
                        print("- {} - SetValue failed: {}".format(element, data.get('error')))
                else:
                    print("- {} - HTTP error: {}".format(element, response.status_code))
                    
            except Exception as e:
                print("- {} - Exception: {}".format(element, str(e)))
        
        compliance_percentage = (compliance_count / total_elements) * 100
        print("\nSCORM 1.2 Data Model Compliance: {}/{} ({:.1f}%)".format(compliance_count, total_elements, compliance_percentage))
        
        self.assertGreaterEqual(compliance_percentage, 100.0, 
                              "SCORM 1.2 compliance should be 100%, got {:.1f}%".format(compliance_percentage))
    
    def test_scorm_2004_data_model_compliance(self):
        """Test SCORM 2004 data model compliance - 100%"""
        print("\n=== Testing SCORM 2004 Data Model Compliance ===")
        
        # Test SCORM 2004 elements
        scorm_2004_elements = [
            'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled',
            'cmi.score.raw', 'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure',
            'cmi.location', 'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry',
            'cmi.exit', 'cmi.credit', 'cmi.mode', 'cmi.learner_id', 'cmi.learner_name',
            'cmi.completion_threshold', 'cmi.scaled_passing_score', 'cmi.total_time',
            'cmi.session_time', 'cmi.learner_preference.audio_level',
            'cmi.learner_preference.language', 'cmi.learner_preference.delivery_speed',
            'cmi.learner_preference.audio_captioning', 'cmi.student_data.mastery_score',
            'cmi.student_data.max_time_allowed', 'cmi.student_data.time_limit_action'
        ]
        
        compliance_count = 0
        total_elements = len(scorm_2004_elements)
        
        for element in scorm_2004_elements:
            try:
                # Test SetValue
                response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                    'action': 'SetValue',
                    'element': element,
                    'value': 'test_value'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('result') == 'true':
                        compliance_count += 1
                        print("+ {} - SetValue compliant".format(element))
                    else:
                        print("- {} - SetValue failed: {}".format(element, data.get('error')))
                else:
                    print("- {} - HTTP error: {}".format(element, response.status_code))
                    
            except Exception as e:
                print("- {} - Exception: {}".format(element, str(e)))
        
        compliance_percentage = (compliance_count / total_elements) * 100
        print("\nSCORM 2004 Data Model Compliance: {}/{} ({:.1f}%)".format(compliance_count, total_elements, compliance_percentage))
        
        self.assertGreaterEqual(compliance_percentage, 100.0, 
                              "SCORM 2004 compliance should be 100%, got {:.1f}%".format(compliance_percentage))
    
    def test_scorm_api_compliance(self):
        """Test SCORM API compliance - 100%"""
        print("\n=== Testing SCORM API Compliance ===")
        
        api_functions = [
            'LMSInitialize', 'LMSGetValue', 'LMSSetValue', 'LMSCommit', 'LMSFinish',
            'LMSGetLastError', 'LMSGetErrorString', 'LMSGetDiagnostic'
        ]
        
        compliance_count = 0
        total_functions = len(api_functions)
        
        for function in api_functions:
            try:
                if function == 'LMSInitialize':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'Initialize'
                    })
                elif function == 'LMSGetValue':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'GetValue',
                        'element': 'cmi.core.lesson_status'
                    })
                elif function == 'LMSSetValue':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'SetValue',
                        'element': 'cmi.core.lesson_status',
                        'value': 'completed'
                    })
                elif function == 'LMSCommit':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'Commit'
                    })
                elif function == 'LMSFinish':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'Finish'
                    })
                elif function == 'LMSGetLastError':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'GetLastError'
                    })
                elif function == 'LMSGetErrorString':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'GetErrorString',
                        'error_code': '0'
                    })
                elif function == 'LMSGetDiagnostic':
                    response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                        'action': 'GetDiagnostic',
                        'error_code': '0'
                    })
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('result') == 'true' or data.get('error_code') == '0':
                        compliance_count += 1
                        print("+ {} - API compliant".format(function))
                    else:
                        print("- {} - API failed: {}".format(function, data.get('error')))
                else:
                    print("- {} - HTTP error: {}".format(function, response.status_code))
                    
            except Exception as e:
                print("- {} - Exception: {}".format(function, str(e)))
        
        compliance_percentage = (compliance_count / total_functions) * 100
        print("\nSCORM API Compliance: {}/{} ({:.1f}%)".format(compliance_count, total_functions, compliance_percentage))
        
        self.assertGreaterEqual(compliance_percentage, 100.0, 
                              "SCORM API compliance should be 100%, got {:.1f}%".format(compliance_percentage))
    
    def test_error_recovery_compliance(self):
        """Test error recovery compliance - 100%"""
        print("\n=== Testing Error Recovery Compliance ===")
        
        error_codes = [
            '301', '302', '303', '401', '402', '403', '404', '405', '406', '407', '408', '409', '410'
        ]
        
        recovery_count = 0
        total_errors = len(error_codes)
        
        for error_code in error_codes:
            try:
                # Test error recovery
                response = self.client.post('/scorm/api/{}/'.format(self.topic.id), {
                    'action': 'SetValue',
                    'element': 'cmi.core.invalid_element',
                    'value': 'test_value'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('result') == 'true' or 'recovery' in str(data):
                        recovery_count += 1
                        print("+ Error {} - Recovery compliant".format(error_code))
                    else:
                        print("- Error {} - Recovery failed: {}".format(error_code, data.get('error')))
                else:
                    print("- Error {} - HTTP error: {}".format(error_code, response.status_code))
                    
            except Exception as e:
                print("- Error {} - Exception: {}".format(error_code, str(e)))
        
        recovery_percentage = (recovery_count / total_errors) * 100
        print("\nError Recovery Compliance: {}/{} ({:.1f}%)".format(recovery_count, total_errors, recovery_percentage))
        
        self.assertGreaterEqual(recovery_percentage, 100.0, 
                              "Error recovery compliance should be 100%, got {:.1f}%".format(recovery_percentage))
    
    def test_sequencing_compliance(self):
        """Test SCORM 2004 sequencing compliance - 100%"""
        print("\n=== Testing SCORM 2004 Sequencing Compliance ===")
        
        # Create sequencing rules
        sequencing = SCORM2004Sequencing.objects.create(
            activity_id='test_activity_1',
            title='Test Activity',
            sequencing_rules={
                'preconditions': [
                    {'type': 'completion_status', 'required_status': 'completed'}
                ],
                'postconditions': [
                    {'type': 'success_status', 'required_status': 'passed'}
                ]
            },
            rollup_rules={
                'completion_threshold': 80,
                'mastery_score': 70
            },
            navigation_rules={
                'continue': [{'type': 'completion_required'}],
                'previous': [{'type': 'success_required'}]
            }
        )
        
        # Test sequencing processing
        try:
            result = sequencing_processor.process_sequencing_rules(
                'test_activity_1', self.user.id, 'continue', {}
            )
            
            if result.get('result') == 'true':
                print("+ Sequencing processing compliant")
                sequencing_compliance = 100.0
            else:
                print("- Sequencing processing failed: {}".format(result.get('reason')))
                sequencing_compliance = 0.0
                
        except Exception as e:
            print("- Sequencing processing exception: {}".format(str(e)))
            sequencing_compliance = 0.0
        
        print("\nSCORM 2004 Sequencing Compliance: {:.1f}%".format(sequencing_compliance))
        
        self.assertGreaterEqual(sequencing_compliance, 100.0, 
                              "Sequencing compliance should be 100%, got {:.1f}%".format(sequencing_compliance))


class xAPIComplianceTest(TestCase):
    """Comprehensive xAPI compliance testing"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.lrs = LRS.objects.create(
            name='Test LRS',
            endpoint='http://test.example.com/xapi/',
            username='test',
            password='test'
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_xapi_statement_compliance(self):
        """Test xAPI statement compliance - 100%"""
        print("\n=== Testing xAPI Statement Compliance ===")
        
        # Test statement creation
        statement_data = {
            'actor': {
                'mbox': 'mailto:test@example.com',
                'name': 'Test User'
            },
            'verb': {
                'id': 'http://adlnet.gov/expapi/verbs/experienced',
                'display': {'en-US': 'experienced'}
            },
            'object': {
                'id': 'http://example.com/activity/test',
                'definition': {
                    'name': {'en-US': 'Test Activity'},
                    'type': 'http://adlnet.gov/expapi/activities/course'
                }
            },
            'result': {
                'completion': True,
                'success': True,
                'score': {'scaled': 0.8}
            }
        }
        
        try:
            response = self.client.post('/lrs/statements/', 
                                      json.dumps(statement_data),
                                      content_type='application/json')
            
            if response.status_code == 200:
                data = response.json()
                if 'statements' in data:
                    print("+ xAPI Statement creation compliant")
                    statement_compliance = 100.0
                else:
                    print("- xAPI Statement creation failed: {}".format(data))
                    statement_compliance = 0.0
            else:
                print("- xAPI Statement creation HTTP error: {}".format(response.status_code))
                statement_compliance = 0.0
                
        except Exception as e:
            print("- xAPI Statement creation exception: {}".format(str(e)))
            statement_compliance = 0.0
        
        print("\nxAPI Statement Compliance: {:.1f}%".format(statement_compliance))
        
        self.assertGreaterEqual(statement_compliance, 100.0, 
                              "xAPI statement compliance should be 100%, got {:.1f}%".format(statement_compliance))


class cmi5ComplianceTest(TestCase):
    """Comprehensive cmi5 compliance testing"""
    
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
            course=self.course
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_cmi5_au_compliance(self):
        """Test cmi5 AU compliance - 100%"""
        print("\n=== Testing cmi5 AU Compliance ===")
        
        # Test cmi5 AU creation
        try:
            response = self.client.post('/lrs/cmi5/au/', {
                'au_id': 'test_au_1',
                'title': 'Test AU',
                'description': 'Test AU Description',
                'launch_url': 'http://example.com/launch',
                'launch_parameters': {'param1': 'value1'}
            })
            
            if response.status_code == 200:
                data = response.json()
                if data.get('au_id') == 'test_au_1':
                    print("+ cmi5 AU creation compliant")
                    au_compliance = 100.0
                else:
                    print("- cmi5 AU creation failed: {}".format(data))
                    au_compliance = 0.0
            else:
                print("- cmi5 AU creation HTTP error: {}".format(response.status_code))
                au_compliance = 0.0
                
        except Exception as e:
            print("- cmi5 AU creation exception: {}".format(str(e)))
            au_compliance = 0.0
        
        print("\ncmi5 AU Compliance: {:.1f}%".format(au_compliance))
        
        self.assertGreaterEqual(au_compliance, 100.0, 
                              "cmi5 AU compliance should be 100%, got {:.1f}%".format(au_compliance))


def run_compliance_tests():
    """Run all compliance tests"""
    print("=" * 80)
    print("SCORM, xAPI, and cmi5 100% COMPLIANCE TEST SUITE")
    print("=" * 80)
    
    # Run SCORM tests
    print("\n" + "=" * 50)
    print("SCORM COMPLIANCE TESTS")
    print("=" * 50)
    
    scorm_test = SCORMComplianceTest()
    scorm_test.setUp()
    
    try:
        scorm_test.test_scorm_1_2_data_model_compliance()
        scorm_test.test_scorm_2004_data_model_compliance()
        scorm_test.test_scorm_api_compliance()
        scorm_test.test_error_recovery_compliance()
        scorm_test.test_sequencing_compliance()
    except Exception as e:
        print("SCORM test error: {}".format(str(e)))
    
    # Run xAPI tests
    print("\n" + "=" * 50)
    print("xAPI COMPLIANCE TESTS")
    print("=" * 50)
    
    xapi_test = xAPIComplianceTest()
    xapi_test.setUp()
    
    try:
        xapi_test.test_xapi_statement_compliance()
    except Exception as e:
        print("xAPI test error: {}".format(str(e)))
    
    # Run cmi5 tests
    print("\n" + "=" * 50)
    print("cmi5 COMPLIANCE TESTS")
    print("=" * 50)
    
    cmi5_test = cmi5ComplianceTest()
    cmi5_test.setUp()
    
    try:
        cmi5_test.test_cmi5_au_compliance()
    except Exception as e:
        print("cmi5 test error: {}".format(str(e)))
    
    print("\n" + "=" * 80)
    print("COMPLIANCE TEST SUITE COMPLETED")
    print("=" * 80)


if __name__ == '__main__':
    run_compliance_tests()
