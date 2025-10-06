# -*- coding: utf-8 -*-
"""
SCORM Compliance Test Suite
Comprehensive testing of SCORM 1.2 and 2004 compliance
"""
import json
import logging
import os
import sys
from django.core.management import execute_from_command_line
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from courses.models import Topic, Course
from scorm.models import ScormPackage, ScormAttempt
from scorm.api_handler_enhanced import ScormAPIHandlerEnhanced
from scorm.scorm_data_model_validator import ScormDataModelValidator

logger = logging.getLogger(__name__)
User = get_user_model()


class ScormComplianceTester:
    """
    Comprehensive SCORM compliance testing
    """
    
    def __init__(self):
        self.test_results = {
            'api_methods': {'passed': 0, 'failed': 0, 'errors': []},
            'data_model': {'passed': 0, 'failed': 0, 'errors': []},
            'error_handling': {'passed': 0, 'failed': 0, 'errors': []},
            'bookmarking': {'passed': 0, 'failed': 0, 'errors': []},
            'scoring': {'passed': 0, 'failed': 0, 'errors': []},
            'time_tracking': {'passed': 0, 'failed': 0, 'errors': []},
        }
    
    def run_all_tests(self):
        """Run all SCORM compliance tests"""
        print("Starting SCORM Compliance Testing...")
        print("="*60)
        
        try:
            # Setup test data
            self._setup_test_data()
            
            # Test SCORM 1.2
            print("\nTesting SCORM 1.2 Compliance...")
            self._test_scorm_12()
            
            # Test SCORM 2004
            print("\nTesting SCORM 2004 Compliance...")
            self._test_scorm_2004()
            
            # Test data model elements
            print("\nTesting Data Model Elements...")
            self._test_data_model_elements()
            
            # Test error handling
            print("\nTesting Error Handling...")
            self._test_error_handling()
            
            # Test bookmarking
            print("\nTesting Bookmarking...")
            self._test_bookmarking()
            
            # Test scoring
            print("\nTesting Scoring...")
            self._test_scoring()
            
            # Test time tracking
            print("\nTesting Time Tracking...")
            self._test_time_tracking()
            
            # Print results
            self._print_results()
            
        except Exception as e:
            logger.error("SCORM compliance testing failed: %s" % str(e))
            print("Error: %s" % str(e))
    
    def _setup_test_data(self):
        """Setup test data for SCORM testing"""
        try:
            # Create test user
            self.user, created = User.objects.get_or_create(
                username='scorm_test_user',
                defaults={
                    'email': 'test@example.com',
                    'first_name': 'Test',
                    'last_name': 'User'
                }
            )
            
            # Create test course
            self.course, created = Course.objects.get_or_create(
                title='SCORM Test Course',
                defaults={'description': 'Test course for SCORM compliance testing'}
            )
            
            # Create test topic
            self.topic, created = Topic.objects.get_or_create(
                title='SCORM Test Topic',
                course=self.course,
                defaults={'description': 'Test topic for SCORM compliance testing'}
            )
            
            # Create SCORM 1.2 package
            self.scorm_12_package, created = ScormPackage.objects.get_or_create(
                topic=self.topic,
                defaults={
                    'version': '1.2',
                    'identifier': 'test_scorm_12',
                    'title': 'SCORM 1.2 Test Package',
                    'package_file': 'test.zip',
                    'extracted_path': '/test/scorm12',
                    'launch_url': 'index.html',
                    'manifest_data': {},
                    'mastery_score': 80
                }
            )
            
            # Create SCORM 2004 package
            self.scorm_2004_package, created = ScormPackage.objects.get_or_create(
                topic=self.topic,
                defaults={
                    'version': '2004',
                    'identifier': 'test_scorm_2004',
                    'title': 'SCORM 2004 Test Package',
                    'package_file': 'test.zip',
                    'extracted_path': '/test/scorm2004',
                    'launch_url': 'index.html',
                    'manifest_data': {},
                    'mastery_score': 80
                }
            )
            
            print("✓ Test data setup completed")
            
        except Exception as e:
            logger.error("Failed to setup test data: %s" % str(e))
            raise
    
    def _test_scorm_12(self):
        """Test SCORM 1.2 compliance"""
        try:
            # Create test attempt
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            # Test API methods
            handler = ScormAPIHandlerEnhanced(attempt)
            
            # Test Initialize
            result = handler.initialize()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 1.2 Initialize: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = "✗ SCORM 1.2 Initialize: FAILED - %s" % result
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test GetValue
            student_id = handler.get_value('cmi.core.student_id')
            if student_id:
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 1.2 GetValue: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = "✗ SCORM 1.2 GetValue: FAILED"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test SetValue
            result = handler.set_value('cmi.core.lesson_status', 'completed')
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 1.2 SetValue: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = "✗ SCORM 1.2 SetValue: FAILED - %s" % result
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test Commit
            result = handler.commit()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 1.2 Commit: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = "✗ SCORM 1.2 Commit: FAILED - %s" % result
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test Terminate
            result = handler.terminate()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 1.2 Terminate: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = f"✗ SCORM 1.2 Terminate: FAILED - {result}"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
        except Exception as e:
            self.test_results['api_methods']['failed'] += 1
            error = f"✗ SCORM 1.2 Testing: Exception - {str(e)}"
            self.test_results['api_methods']['errors'].append(error)
            print(error)
    
    def _test_scorm_2004(self):
        """Test SCORM 2004 compliance"""
        try:
            # Create test attempt
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_2004_package,
                defaults={'attempt_number': 1}
            )
            
            # Test API methods
            handler = ScormAPIHandlerEnhanced(attempt)
            
            # Test Initialize
            result = handler.initialize()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 2004 Initialize: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = f"✗ SCORM 2004 Initialize: FAILED - {result}"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test GetValue
            learner_id = handler.get_value('cmi.learner_id')
            if learner_id:
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 2004 GetValue: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = "✗ SCORM 2004 GetValue: FAILED"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test SetValue
            result = handler.set_value('cmi.completion_status', 'completed')
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 2004 SetValue: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = f"✗ SCORM 2004 SetValue: FAILED - {result}"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test Commit
            result = handler.commit()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 2004 Commit: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = f"✗ SCORM 2004 Commit: FAILED - {result}"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
            # Test Terminate
            result = handler.terminate()
            if result == 'true':
                self.test_results['api_methods']['passed'] += 1
                print("✓ SCORM 2004 Terminate: PASSED")
            else:
                self.test_results['api_methods']['failed'] += 1
                error = f"✗ SCORM 2004 Terminate: FAILED - {result}"
                self.test_results['api_methods']['errors'].append(error)
                print(error)
            
        except Exception as e:
            self.test_results['api_methods']['failed'] += 1
            error = f"✗ SCORM 2004 Testing: Exception - {str(e)}"
            self.test_results['api_methods']['errors'].append(error)
            print(error)
    
    def _test_data_model_elements(self):
        """Test data model elements"""
        try:
            # Test SCORM 1.2 data model
            attempt_12, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            handler_12 = ScormAPIHandlerEnhanced(attempt_12)
            handler_12.initialize()
            
            # Test core elements
            core_elements = [
                'cmi.core.student_id',
                'cmi.core.student_name',
                'cmi.core.lesson_location',
                'cmi.core.credit',
                'cmi.core.lesson_status',
                'cmi.core.entry',
                'cmi.core.score.raw',
                'cmi.core.score.max',
                'cmi.core.score.min',
                'cmi.core.total_time',
                'cmi.core.lesson_mode',
                'cmi.suspend_data',
                'cmi.launch_data',
                'cmi.comments',
                'cmi.comments_from_lms'
            ]
            
            for element in core_elements:
                value = handler_12.get_value(element)
                if value is not None:
                    self.test_results['data_model']['passed'] += 1
                    print(f"✓ SCORM 1.2 {element}: {value}")
                else:
                    self.test_results['data_model']['failed'] += 1
                    error = f"✗ SCORM 1.2 {element}: FAILED"
                    self.test_results['data_model']['errors'].append(error)
                    print(error)
            
            handler_12.terminate()
            
            # Test SCORM 2004 data model
            attempt_2004, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_2004_package,
                defaults={'attempt_number': 1}
            )
            
            handler_2004 = ScormAPIHandlerEnhanced(attempt_2004)
            handler_2004.initialize()
            
            # Test core elements
            core_elements_2004 = [
                'cmi._version',
                'cmi.learner_id',
                'cmi.learner_name',
                'cmi.location',
                'cmi.credit',
                'cmi.completion_status',
                'cmi.success_status',
                'cmi.entry',
                'cmi.total_time',
                'cmi.session_time',
                'cmi.suspend_data',
                'cmi.launch_data',
                'cmi.mode',
                'cmi.progress_measure',
                'cmi.max_time_allowed',
                'cmi.time_limit_action'
            ]
            
            for element in core_elements_2004:
                value = handler_2004.get_value(element)
                if value is not None:
                    self.test_results['data_model']['passed'] += 1
                    print(f"✓ SCORM 2004 {element}: {value}")
                else:
                    self.test_results['data_model']['failed'] += 1
                    error = f"✗ SCORM 2004 {element}: FAILED"
                    self.test_results['data_model']['errors'].append(error)
                    print(error)
            
            handler_2004.terminate()
            
        except Exception as e:
            self.test_results['data_model']['failed'] += 1
            error = f"✗ Data Model Testing: Exception - {str(e)}"
            self.test_results['data_model']['errors'].append(error)
            print(error)
    
    def _test_error_handling(self):
        """Test error handling"""
        try:
            # Test uninitialized API calls
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            handler = ScormAPIHandlerEnhanced(attempt)
            
            # Test GetValue before Initialize
            result = handler.get_value('cmi.core.student_id')
            if result == '':
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Uninitialized GetValue: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = "✗ Error Handling - Uninitialized GetValue: FAILED"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
            # Test SetValue before Initialize
            result = handler.set_value('cmi.core.lesson_status', 'completed')
            if result == 'false':
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Uninitialized SetValue: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = "✗ Error Handling - Uninitialized SetValue: FAILED"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
            # Test Commit before Initialize
            result = handler.commit()
            if result == 'false':
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Uninitialized Commit: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = "✗ Error Handling - Uninitialized Commit: FAILED"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
            # Test Terminate before Initialize
            result = handler.terminate()
            if result == 'false':
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Uninitialized Terminate: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = "✗ Error Handling - Uninitialized Terminate: FAILED"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
            # Test error codes
            error_code = handler.get_last_error()
            if error_code == '301':  # Not initialized
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Error Code: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = f"✗ Error Handling - Error Code: FAILED - {error_code}"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
            # Test error string
            error_string = handler.get_error_string('301')
            if error_string == 'Not initialized':
                self.test_results['error_handling']['passed'] += 1
                print("✓ Error Handling - Error String: PASSED")
            else:
                self.test_results['error_handling']['failed'] += 1
                error = f"✗ Error Handling - Error String: FAILED - {error_string}"
                self.test_results['error_handling']['errors'].append(error)
                print(error)
            
        except Exception as e:
            self.test_results['error_handling']['failed'] += 1
            error = f"✗ Error Handling Testing: Exception - {str(e)}"
            self.test_results['error_handling']['errors'].append(error)
            print(error)
    
    def _test_bookmarking(self):
        """Test bookmarking functionality"""
        try:
            # Test SCORM 1.2 bookmarking
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            handler = ScormAPIHandlerEnhanced(attempt)
            handler.initialize()
            
            # Test lesson location
            result = handler.set_value('cmi.core.lesson_location', 'lesson_2')
            if result == 'true':
                self.test_results['bookmarking']['passed'] += 1
                print("✓ Bookmarking - Set Location: PASSED")
            else:
                self.test_results['bookmarking']['failed'] += 1
                error = f"✗ Bookmarking - Set Location: FAILED - {result}"
                self.test_results['bookmarking']['errors'].append(error)
                print(error)
            
            # Test suspend data
            result = handler.set_value('cmi.suspend_data', 'bookmark_data_123')
            if result == 'true':
                self.test_results['bookmarking']['passed'] += 1
                print("✓ Bookmarking - Set Suspend Data: PASSED")
            else:
                self.test_results['bookmarking']['failed'] += 1
                error = f"✗ Bookmarking - Set Suspend Data: FAILED - {result}"
                self.test_results['bookmarking']['errors'].append(error)
                print(error)
            
            # Test retrieval
            location = handler.get_value('cmi.core.lesson_location')
            if location == 'lesson_2':
                self.test_results['bookmarking']['passed'] += 1
                print("✓ Bookmarking - Get Location: PASSED")
            else:
                self.test_results['bookmarking']['failed'] += 1
                error = f"✗ Bookmarking - Get Location: FAILED - {location}"
                self.test_results['bookmarking']['errors'].append(error)
                print(error)
            
            suspend_data = handler.get_value('cmi.suspend_data')
            if suspend_data == 'bookmark_data_123':
                self.test_results['bookmarking']['passed'] += 1
                print("✓ Bookmarking - Get Suspend Data: PASSED")
            else:
                self.test_results['bookmarking']['failed'] += 1
                error = f"✗ Bookmarking - Get Suspend Data: FAILED - {suspend_data}"
                self.test_results['bookmarking']['errors'].append(error)
                print(error)
            
            handler.terminate()
            
        except Exception as e:
            self.test_results['bookmarking']['failed'] += 1
            error = f"✗ Bookmarking Testing: Exception - {str(e)}"
            self.test_results['bookmarking']['errors'].append(error)
            print(error)
    
    def _test_scoring(self):
        """Test scoring functionality"""
        try:
            # Test SCORM 1.2 scoring
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            handler = ScormAPIHandlerEnhanced(attempt)
            handler.initialize()
            
            # Test score setting
            result = handler.set_value('cmi.core.score.raw', '85')
            if result == 'true':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Set Raw Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Set Raw Score: FAILED - {result}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            # Test score retrieval
            score = handler.get_value('cmi.core.score.raw')
            if score == '85':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Get Raw Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Get Raw Score: FAILED - {score}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            # Test max score
            result = handler.set_value('cmi.core.score.max', '100')
            if result == 'true':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Set Max Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Set Max Score: FAILED - {result}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            # Test min score
            result = handler.set_value('cmi.core.score.min', '0')
            if result == 'true':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Set Min Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Set Min Score: FAILED - {result}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            handler.terminate()
            
            # Test SCORM 2004 scoring
            attempt_2004, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_2004_package,
                defaults={'attempt_number': 1}
            )
            
            handler_2004 = ScormAPIHandlerEnhanced(attempt_2004)
            handler_2004.initialize()
            
            # Test scaled score
            result = handler_2004.set_value('cmi.score.scaled', '0.85')
            if result == 'true':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Set Scaled Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Set Scaled Score: FAILED - {result}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            # Test scaled score retrieval
            scaled_score = handler_2004.get_value('cmi.score.scaled')
            if scaled_score == '0.85':
                self.test_results['scoring']['passed'] += 1
                print("✓ Scoring - Get Scaled Score: PASSED")
            else:
                self.test_results['scoring']['failed'] += 1
                error = f"✗ Scoring - Get Scaled Score: FAILED - {scaled_score}"
                self.test_results['scoring']['errors'].append(error)
                print(error)
            
            handler_2004.terminate()
            
        except Exception as e:
            self.test_results['scoring']['failed'] += 1
            error = f"✗ Scoring Testing: Exception - {str(e)}"
            self.test_results['scoring']['errors'].append(error)
            print(error)
    
    def _test_time_tracking(self):
        """Test time tracking functionality"""
        try:
            # Test SCORM 1.2 time tracking
            attempt, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_12_package,
                defaults={'attempt_number': 1}
            )
            
            handler = ScormAPIHandlerEnhanced(attempt)
            handler.initialize()
            
            # Test session time
            result = handler.set_value('cmi.core.session_time', '00:05:30.00')
            if result == 'true':
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Set Session Time: PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = f"✗ Time Tracking - Set Session Time: FAILED - {result}"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            # Test total time
            result = handler.set_value('cmi.core.total_time', '00:10:45.50')
            if result == 'true':
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Set Total Time: PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = f"✗ Time Tracking - Set Total Time: FAILED - {result}"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            # Test time retrieval
            session_time = handler.get_value('cmi.core.session_time')
            if session_time:
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Get Session Time: PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = "✗ Time Tracking - Get Session Time: FAILED"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            total_time = handler.get_value('cmi.core.total_time')
            if total_time:
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Get Total Time: PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = "✗ Time Tracking - Get Total Time: FAILED"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            handler.terminate()
            
            # Test SCORM 2004 time tracking
            attempt_2004, created = ScormAttempt.objects.get_or_create(
                user=self.user,
                scorm_package=self.scorm_2004_package,
                defaults={'attempt_number': 1}
            )
            
            handler_2004 = ScormAPIHandlerEnhanced(attempt_2004)
            handler_2004.initialize()
            
            # Test session time (ISO 8601 format)
            result = handler_2004.set_value('cmi.session_time', 'PT5M30S')
            if result == 'true':
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Set Session Time (ISO): PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = f"✗ Time Tracking - Set Session Time (ISO): FAILED - {result}"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            # Test total time (ISO 8601 format)
            result = handler_2004.set_value('cmi.total_time', 'PT10M45S')
            if result == 'true':
                self.test_results['time_tracking']['passed'] += 1
                print("✓ Time Tracking - Set Total Time (ISO): PASSED")
            else:
                self.test_results['time_tracking']['failed'] += 1
                error = f"✗ Time Tracking - Set Total Time (ISO): FAILED - {result}"
                self.test_results['time_tracking']['errors'].append(error)
                print(error)
            
            handler_2004.terminate()
            
        except Exception as e:
            self.test_results['time_tracking']['failed'] += 1
            error = f"✗ Time Tracking Testing: Exception - {str(e)}"
            self.test_results['time_tracking']['errors'].append(error)
            print(error)
    
    def _print_results(self):
        """Print test results summary"""
        print("\n" + "="*60)
        print("SCORM COMPLIANCE TEST RESULTS")
        print("="*60)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            print(f"\n{category.upper().replace('_', ' ')} Results:")
            print(f"  Passed: {results['passed']}")
            print(f"  Failed: {results['failed']}")
            print(f"  Total: {results['passed'] + results['failed']}")
            
            total_passed += results['passed']
            total_failed += results['failed']
            
            if results['errors']:
                print(f"\nErrors:")
                for error in results['errors']:
                    print(f"  {error}")
        
        print(f"\nOVERALL RESULTS:")
        print(f"  Total Passed: {total_passed}")
        print(f"  Total Failed: {total_failed}")
        print(f"  Total Tests: {total_passed + total_failed}")
        print(f"  Success Rate: {(total_passed / (total_passed + total_failed)) * 100:.1f}%")
        
        print("\n" + "="*60)


def main():
    """Main function to run SCORM compliance tests"""
    tester = ScormComplianceTester()
    tester.run_all_tests()


if __name__ == '__main__':
    main()
