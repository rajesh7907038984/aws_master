# -*- coding: utf-8 -*-
"""
SCORM Data Model Validator
Comprehensive validation of SCORM 1.2 and 2004 data model elements
"""
import json
import logging
from django.test import TestCase
from django.contrib.auth import get_user_model
from courses.models import Topic, Course
from .models import ScormPackage, ScormAttempt
from .api_handler_enhanced import ScormAPIHandlerEnhanced

logger = logging.getLogger(__name__)

User = get_user_model()


class ScormDataModelValidator:
    """
    Validator for SCORM 1.2 and 2004 data model elements
    """
    
    # SCORM 1.2 Core Elements
    SCORM_12_CORE_ELEMENTS = {
        'cmi.core._children': 'C',
        'cmi.core.student_id': 'RO',
        'cmi.core.student_name': 'RO',
        'cmi.core.lesson_location': 'RW',
        'cmi.core.credit': 'RO',
        'cmi.core.lesson_status': 'RW',
        'cmi.core.entry': 'RO',
        'cmi.core.score._children': 'C',
        'cmi.core.score.raw': 'RW',
        'cmi.core.score.max': 'RW',
        'cmi.core.score.min': 'RW',
        'cmi.core.total_time': 'RO',
        'cmi.core.lesson_mode': 'RO',
        'cmi.core.exit': 'WO',
        'cmi.core.session_time': 'WO',
        'cmi.suspend_data': 'RW',
        'cmi.launch_data': 'RO',
        'cmi.comments': 'RW',
        'cmi.comments_from_lms': 'RO',
    }
    
    # SCORM 1.2 Student Data Elements
    SCORM_12_STUDENT_DATA = {
        'cmi.student_data._children': 'C',
        'cmi.student_data.mastery_score': 'RO',
        'cmi.student_data.max_time_allowed': 'RO',
        'cmi.student_data.time_limit_action': 'RO',
    }
    
    # SCORM 1.2 Student Preference Elements
    SCORM_12_PREFERENCES = {
        'cmi.student_preference._children': 'C',
        'cmi.student_preference.audio': 'RW',
        'cmi.student_preference.language': 'RW',
        'cmi.student_preference.speed': 'RW',
        'cmi.student_preference.text': 'RW',
    }
    
    # SCORM 1.2 Interactions Elements
    SCORM_12_INTERACTIONS = {
        'cmi.interactions._children': 'C',
        'cmi.interactions._count': 'C',
        'cmi.interactions.n.id': 'RW',
        'cmi.interactions.n.objectives.m.id': 'RW',
        'cmi.interactions.n.time': 'RW',
        'cmi.interactions.n.type': 'RW',
        'cmi.interactions.n.correct_responses.k.pattern': 'RW',
        'cmi.interactions.n.weighting': 'RW',
        'cmi.interactions.n.student_response': 'RW',
        'cmi.interactions.n.result': 'RW',
        'cmi.interactions.n.latency': 'RW',
    }
    
    # SCORM 1.2 Objectives Elements
    SCORM_12_OBJECTIVES = {
        'cmi.objectives._children': 'C',
        'cmi.objectives._count': 'C',
        'cmi.objectives.n.id': 'RW',
        'cmi.objectives.n.score.raw': 'RW',
        'cmi.objectives.n.score.min': 'RW',
        'cmi.objectives.n.score.max': 'RW',
        'cmi.objectives.n.status': 'RW',
    }
    
    # SCORM 2004 Core Elements
    SCORM_2004_CORE_ELEMENTS = {
        'cmi._version': 'RO',
        'cmi.learner_id': 'RO',
        'cmi.learner_name': 'RO',
        'cmi.location': 'RW',
        'cmi.credit': 'RO',
        'cmi.completion_status': 'RW',
        'cmi.success_status': 'RW',
        'cmi.entry': 'RO',
        'cmi.exit': 'WO',
        'cmi.total_time': 'RO',
        'cmi.session_time': 'WO',
        'cmi.suspend_data': 'RW',
        'cmi.launch_data': 'RO',
        'cmi.mode': 'RO',
        'cmi.progress_measure': 'RW',
        'cmi.max_time_allowed': 'RO',
        'cmi.time_limit_action': 'RO',
    }
    
    # SCORM 2004 Score Elements
    SCORM_2004_SCORE_ELEMENTS = {
        'cmi.score._children': 'C',
        'cmi.score.raw': 'RW',
        'cmi.score.min': 'RW',
        'cmi.score.max': 'RW',
        'cmi.score.scaled': 'RW',
    }
    
    # SCORM 2004 Objectives Elements
    SCORM_2004_OBJECTIVES = {
        'cmi.objectives._children': 'C',
        'cmi.objectives._count': 'C',
        'cmi.objectives.n.id': 'RW',
        'cmi.objectives.n.score.raw': 'RW',
        'cmi.objectives.n.score.min': 'RW',
        'cmi.objectives.n.score.max': 'RW',
        'cmi.objectives.n.score.scaled': 'RW',
        'cmi.objectives.n.success_status': 'RW',
        'cmi.objectives.n.completion_status': 'RW',
        'cmi.objectives.n.progress_measure': 'RW',
        'cmi.objectives.n.description': 'RW',
    }
    
    # SCORM 2004 Interactions Elements
    SCORM_2004_INTERACTIONS = {
        'cmi.interactions._children': 'C',
        'cmi.interactions._count': 'C',
        'cmi.interactions.n.id': 'RW',
        'cmi.interactions.n.type': 'RW',
        'cmi.interactions.n.timestamp': 'RW',
        'cmi.interactions.n.weighting': 'RW',
        'cmi.interactions.n.learner_response': 'RW',
        'cmi.interactions.n.result': 'RW',
        'cmi.interactions.n.latency': 'RW',
        'cmi.interactions.n.description': 'RW',
        'cmi.interactions.n.correct_responses.k.pattern': 'RW',
        'cmi.interactions.n.objectives.m.id': 'RW',
    }
    
    # SCORM 2004 Learner Preference Elements
    SCORM_2004_PREFERENCES = {
        'cmi.learner_preference._children': 'C',
        'cmi.learner_preference.audio_level': 'RW',
        'cmi.learner_preference.language': 'RW',
        'cmi.learner_preference.delivery_speed': 'RW',
        'cmi.learner_preference.audio_captioning': 'RW',
    }
    
    # SCORM 2004 Comments Elements
    SCORM_2004_COMMENTS = {
        'cmi.comments_from_learner._children': 'C',
        'cmi.comments_from_learner._count': 'C',
        'cmi.comments_from_learner.n.comment': 'RW',
        'cmi.comments_from_learner.n.location': 'RW',
        'cmi.comments_from_learner.n.timestamp': 'RW',
        'cmi.comments_from_lms._children': 'C',
        'cmi.comments_from_lms._count': 'C',
        'cmi.comments_from_lms.n.comment': 'RO',
        'cmi.comments_from_lms.n.location': 'RO',
        'cmi.comments_from_lms.n.timestamp': 'RO',
    }
    
    def __init__(self):
        self.test_results = {
            'scorm_12': {'passed': 0, 'failed': 0, 'errors': []},
            'scorm_2004': {'passed': 0, 'failed': 0, 'errors': []}
        }
    
    def validate_scorm_12_elements(self, handler):
        """Validate SCORM 1.2 data model elements"""
        logger.info("Validating SCORM 1.2 data model elements...")
        
        # Test core elements
        self._test_core_elements(handler, self.SCORM_12_CORE_ELEMENTS, 'scorm_12')
        
        # Test student data elements
        self._test_student_data_elements(handler, self.SCORM_12_STUDENT_DATA, 'scorm_12')
        
        # Test preference elements
        self._test_preference_elements(handler, self.SCORM_12_PREFERENCES, 'scorm_12')
        
        # Test interactions elements
        self._test_interactions_elements(handler, self.SCORM_12_INTERACTIONS, 'scorm_12')
        
        # Test objectives elements
        self._test_objectives_elements(handler, self.SCORM_12_OBJECTIVES, 'scorm_12')
    
    def validate_scorm_2004_elements(self, handler):
        """Validate SCORM 2004 data model elements"""
        logger.info("Validating SCORM 2004 data model elements...")
        
        # Test core elements
        self._test_core_elements(handler, self.SCORM_2004_CORE_ELEMENTS, 'scorm_2004')
        
        # Test score elements
        self._test_score_elements(handler, self.SCORM_2004_SCORE_ELEMENTS, 'scorm_2004')
        
        # Test objectives elements
        self._test_objectives_elements(handler, self.SCORM_2004_OBJECTIVES, 'scorm_2004')
        
        # Test interactions elements
        self._test_interactions_elements(handler, self.SCORM_2004_INTERACTIONS, 'scorm_2004')
        
        # Test preference elements
        self._test_preference_elements(handler, self.SCORM_2004_PREFERENCES, 'scorm_2004')
        
        # Test comments elements
        self._test_comments_elements(handler, self.SCORM_2004_COMMENTS, 'scorm_2004')
    
    def _test_core_elements(self, handler, elements, version):
        """Test core SCORM elements"""
        for element, access_type in elements.items():
            try:
                # Test GetValue
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
                
                # Test SetValue for RW elements
                if access_type == 'RW':
                    test_value = self._get_test_value(element)
                    result = handler.set_value(element, test_value)
                    if result == 'true':
                        self.test_results[version]['passed'] += 1
                        logger.info(f"✓ {element} (SetValue): {test_value}")
                    else:
                        self.test_results[version]['failed'] += 1
                        error = f"✗ {element} (SetValue): failed"
                        self.test_results[version]['errors'].append(error)
                        logger.error(error)
                
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_student_data_elements(self, handler, elements, version):
        """Test student data elements"""
        for element, access_type in elements.items():
            try:
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_preference_elements(self, handler, elements, version):
        """Test preference elements"""
        for element, access_type in elements.items():
            try:
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
                
                # Test SetValue for RW elements
                if access_type == 'RW':
                    test_value = self._get_test_value(element)
                    result = handler.set_value(element, test_value)
                    if result == 'true':
                        self.test_results[version]['passed'] += 1
                        logger.info(f"✓ {element} (SetValue): {test_value}")
                    else:
                        self.test_results[version]['failed'] += 1
                        error = f"✗ {element} (SetValue): failed"
                        self.test_results[version]['errors'].append(error)
                        logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_score_elements(self, handler, elements, version):
        """Test score elements"""
        for element, access_type in elements.items():
            try:
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
                
                # Test SetValue for RW elements
                if access_type == 'RW':
                    test_value = self._get_test_value(element)
                    result = handler.set_value(element, test_value)
                    if result == 'true':
                        self.test_results[version]['passed'] += 1
                        logger.info(f"✓ {element} (SetValue): {test_value}")
                    else:
                        self.test_results[version]['failed'] += 1
                        error = f"✗ {element} (SetValue): failed"
                        self.test_results[version]['errors'].append(error)
                        logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_interactions_elements(self, handler, elements, version):
        """Test interactions elements"""
        for element, access_type in elements.items():
            try:
                # Skip array elements for now
                if 'n.' in element:
                    continue
                
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_objectives_elements(self, handler, elements, version):
        """Test objectives elements"""
        for element, access_type in elements.items():
            try:
                # Skip array elements for now
                if 'n.' in element:
                    continue
                
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _test_comments_elements(self, handler, elements, version):
        """Test comments elements"""
        for element, access_type in elements.items():
            try:
                # Skip array elements for now
                if 'n.' in element:
                    continue
                
                value = handler.get_value(element)
                if value is not None:
                    self.test_results[version]['passed'] += 1
                    logger.info(f"✓ {element} (GetValue): {value}")
                else:
                    self.test_results[version]['failed'] += 1
                    error = f"✗ {element} (GetValue): returned None"
                    self.test_results[version]['errors'].append(error)
                    logger.error(error)
            except Exception as e:
                self.test_results[version]['failed'] += 1
                error = f"✗ {element}: Exception - {str(e)}"
                self.test_results[version]['errors'].append(error)
                logger.error(error)
    
    def _get_test_value(self, element):
        """Get appropriate test value for element"""
        if 'score' in element:
            if 'scaled' in element:
                return '0.8'
            else:
                return '85'
        elif 'status' in element:
            return 'completed'
        elif 'entry' in element:
            return 'ab-initio'
        elif 'location' in element:
            return 'lesson_1'
        elif 'suspend_data' in element:
            return 'bookmark_data'
        elif 'audio' in element:
            return '1'
        elif 'language' in element:
            return 'en'
        elif 'speed' in element:
            return '1.0'
        elif 'text' in element:
            return '1'
        elif 'comment' in element:
            return 'Test comment'
        elif 'timestamp' in element:
            return '2024-01-01T12:00:00.000Z'
        else:
            return 'test_value'
    
    def get_test_results(self):
        """Get test results summary"""
        return self.test_results
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*60)
        print("SCORM DATA MODEL VALIDATION RESULTS")
        print("="*60)
        
        for version, results in self.test_results.items():
            print(f"\n{version.upper()} Results:")
            print(f"  Passed: {results['passed']}")
            print(f"  Failed: {results['failed']}")
            print(f"  Total: {results['passed'] + results['failed']}")
            
            if results['errors']:
                print(f"\nErrors:")
                for error in results['errors']:
                    print(f"  {error}")
        
        print("\n" + "="*60)


def run_scorm_validation():
    """Run SCORM data model validation"""
    try:
        # Create test user
        user, created = User.objects.get_or_create(
            username='scorm_test_user',
            defaults={'email': 'test@example.com', 'first_name': 'Test', 'last_name': 'User'}
        )
        
        # Create test course and topic
        course, created = Course.objects.get_or_create(
            title='SCORM Test Course',
            defaults={'description': 'Test course for SCORM validation'}
        )
        
        topic, created = Topic.objects.get_or_create(
            title='SCORM Test Topic',
            course=course,
            defaults={'description': 'Test topic for SCORM validation'}
        )
        
        # Create SCORM packages for both versions
        scorm_12_package, created = ScormPackage.objects.get_or_create(
            topic=topic,
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
        
        scorm_2004_package, created = ScormPackage.objects.get_or_create(
            topic=topic,
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
        
        # Create test attempts
        attempt_12, created = ScormAttempt.objects.get_or_create(
            user=user,
            scorm_package=scorm_12_package,
            defaults={'attempt_number': 1}
        )
        
        attempt_2004, created = ScormAttempt.objects.get_or_create(
            user=user,
            scorm_package=scorm_2004_package,
            defaults={'attempt_number': 1}
        )
        
        # Initialize validators
        validator = ScormDataModelValidator()
        
        # Test SCORM 1.2
        handler_12 = ScormAPIHandlerEnhanced(attempt_12)
        handler_12.initialize()
        validator.validate_scorm_12_elements(handler_12)
        handler_12.terminate()
        
        # Test SCORM 2004
        handler_2004 = ScormAPIHandlerEnhanced(attempt_2004)
        handler_2004.initialize()
        validator.validate_scorm_2004_elements(handler_2004)
        handler_2004.terminate()
        
        # Print results
        validator.print_summary()
        
        return validator.get_test_results()
        
    except Exception as e:
        logger.error(f"SCORM validation failed: {str(e)}")
        return None


if __name__ == '__main__':
    run_scorm_validation()
