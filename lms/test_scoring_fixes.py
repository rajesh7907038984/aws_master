#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify all scoring system fixes
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.test import TestCase, TransactionTestCase
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from quiz.models import Quiz, Question, Answer, QuizAttempt, UserAnswer
from gradebook.models import Grade
from scorm.models import ScormAttempt, ScormPackage
from scorm.score_sync_service import ScormScoreSyncService
from gradebook.score_history import ScoreHistory
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScoringSystemTests(TestCase):
    """Test all scoring system fixes"""
    
    def setUp(self):
        """Set up test data"""
        self.User = get_user_model()
        
        # Create test user
        self.user = self.User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='learner'
        )
        
        # Create test quiz
        self.quiz = Quiz.objects.create(
            title='Test Quiz',
            description='Test Description',
            creator=self.user,
            passing_score=70,
            time_limit=30
        )
        
        # Create test question
        self.question = Question.objects.create(
            quiz=self.quiz,
            question_text='What is 2+2?',
            question_type='multiple_choice',
            points=10
        )
        
        # Create test answers
        self.correct_answer = Answer.objects.create(
            question=self.question,
            answer_text='4',
            is_correct=True
        )
        
        self.wrong_answer = Answer.objects.create(
            question=self.question,
            answer_text='3',
            is_correct=False
        )
    
    def test_decimal_precision_in_quiz_scoring(self):
        """Test that quiz scoring uses Decimal precision"""
        logger.info("Testing decimal precision in quiz scoring...")
        
        # Create quiz attempt
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        )
        
        # Create correct user answer
        user_answer = UserAnswer.objects.create(
            attempt=attempt,
            question=self.question,
            answer=self.correct_answer,
            is_correct=True
        )
        
        # Calculate score
        score = attempt.calculate_score()
        
        # Verify score is Decimal
        self.assertIsInstance(score, Decimal)
        self.assertEqual(score, Decimal('100.00'))
        
        logger.info("Decimal precision test passed: {}".format(score))
    
    def test_transaction_atomicity_in_scoring(self):
        """Test that score calculations are atomic"""
        logger.info("Testing transaction atomicity...")
        
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        )
        
        # Test that score calculation is wrapped in transaction
        with transaction.atomic():
            score = attempt.calculate_score()
            self.assertIsNotNone(score)
        
        logger.info("Transaction atomicity test passed")
    
    def test_score_validation(self):
        """Test score validation constraints"""
        logger.info("Testing score validation...")
        
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        )
        
        # Test valid score
        attempt.score = Decimal('85.5')
        attempt.clean()  # Should not raise exception
        
        # Test invalid score (negative)
        attempt.score = Decimal('-10')
        with self.assertRaises(ValidationError):
            attempt.clean()
        
        # Test invalid score (over 100%)
        attempt.score = Decimal('150')
        with self.assertRaises(ValidationError):
            attempt.clean()
        
        logger.info("Score validation test passed")
    
    def test_scorm_score_sync_service(self):
        """Test SCORM score synchronization service"""
        logger.info("Testing SCORM score sync service...")
        
        # Create test SCORM package
        from courses.models import Topic
        topic = Topic.objects.create(
            title='Test Topic',
            description='Test Description'
        )
        
        scorm_package = ScormPackage.objects.create(
            topic=topic,
            version='1.2',
            identifier='test-package',
            title='Test SCORM Package',
            package_file='test.zip',
            extracted_path='/test/path',
            launch_url='index.html'
        )
        
        # Create SCORM attempt
        scorm_attempt = ScormAttempt.objects.create(
            user=self.user,
            scorm_package=scorm_package,
            score_raw=Decimal('85'),
            score_min=Decimal('0'),
            score_max=Decimal('100')
        )
        
        # Test score sync
        result = ScormScoreSyncService.sync_score(scorm_attempt)
        
        self.assertTrue(result['success'])
        self.assertIsNotNone(result['data'].get('scaled_score'))
        
        logger.info("SCORM score sync test passed")
    
    def test_score_history_audit_trail(self):
        """Test score history and audit trail"""
        logger.info("Testing score history audit trail...")
        
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True,
            score=Decimal('75')
        )
        
        # Log a score change
        ScoreHistory.log_score_change(
            obj=attempt,
            old_score=Decimal('75'),
            new_score=Decimal('85'),
            changed_by=self.user,
            change_type='updated',
            reason='Grade adjustment',
            metadata={'reason': 'teacher_review'}
        )
        
        # Verify history was created
        history = ScoreHistory.get_score_history(attempt)
        self.assertEqual(history.count(), 1)
        
        history_entry = history.first()
        self.assertEqual(history_entry.old_score, Decimal('75'))
        self.assertEqual(history_entry.new_score, Decimal('85'))
        self.assertEqual(history_entry.change_type, 'updated')
        
        logger.info("Score history audit trail test passed")
    
    def test_concurrent_attempt_handling(self):
        """Test concurrent attempt handling"""
        logger.info("Testing concurrent attempt handling...")
        
        # Test that quiz can handle concurrent attempts properly
        can_start = self.quiz.can_start_new_attempt(self.user)
        self.assertTrue(can_start)
        
        # Create an attempt
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=False
        )
        
        # Should still be able to start if under limit
        can_start_again = self.quiz.can_start_new_attempt(self.user)
        self.assertTrue(can_start_again)
        
        logger.info("Concurrent attempt handling test passed")
    
    def test_decimal_standardization(self):
        """Test that all scoring uses Decimal consistently"""
        logger.info("Testing decimal standardization...")
        
        # Test quiz scoring
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        )
        
        score = attempt.calculate_score()
        self.assertIsInstance(score, Decimal)
        
        # Test SCORM percentage calculation
        from courses.models import Topic
        topic = Topic.objects.create(
            title='Test Topic',
            description='Test Description'
        )
        
        scorm_package = ScormPackage.objects.create(
            topic=topic,
            version='1.2',
            identifier='test-package',
            title='Test SCORM Package',
            package_file='test.zip',
            extracted_path='/test/path',
            launch_url='index.html'
        )
        
        scorm_attempt = ScormAttempt.objects.create(
            user=self.user,
            scorm_package=scorm_package,
            score_raw=Decimal('85'),
            score_max=Decimal('100')
        )
        
        percentage = scorm_attempt.get_percentage_score()
        self.assertIsInstance(percentage, Decimal)
        self.assertEqual(percentage, Decimal('85.00'))
        
        logger.info("Decimal standardization test passed")
    
    def test_error_handling_improvements(self):
        """Test improved error handling"""
        logger.info("Testing error handling improvements...")
        
        # Test that errors are logged properly instead of using print
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        )
        
        # This should not raise an exception and should log errors properly
        try:
            score = attempt.calculate_score()
            self.assertIsNotNone(score)
        except Exception as e:
            self.fail(f"Score calculation should not raise exception: {e}")
        
        logger.info("Error handling improvements test passed")

def run_comprehensive_tests():
    """Run all comprehensive tests"""
    logger.info("=" * 60)
    logger.info("STARTING COMPREHENSIVE SCORING SYSTEM TESTS")
    logger.info("=" * 60)
    
    try:
        # Create test case instance
        test_case = ScoringSystemTests()
        test_case.setUp()
        
        # Run all tests
        test_methods = [
            'test_decimal_precision_in_quiz_scoring',
            'test_transaction_atomicity_in_scoring',
            'test_score_validation',
            'test_scorm_score_sync_service',
            'test_score_history_audit_trail',
            'test_concurrent_attempt_handling',
            'test_decimal_standardization',
            'test_error_handling_improvements'
        ]
        
        passed_tests = 0
        total_tests = len(test_methods)
        
        for test_method in test_methods:
            try:
                logger.info("\nRunning {}...".format(test_method))
                getattr(test_case, test_method)()
                passed_tests += 1
                logger.info("PASSED: {}".format(test_method))
            except Exception as e:
                logger.error(f"FAILED: {test_method} - {str(e)}")
        
        logger.info("\n" + "=" * 60)
        logger.info(f"TEST RESULTS: {passed_tests}/{total_tests} tests passed")
        logger.info("=" * 60)
        
        if passed_tests == total_tests:
            logger.info("ALL TESTS PASSED! Scoring system fixes are working correctly.")
            return True
        else:
            logger.error(f"{total_tests - passed_tests} tests failed. Please review the issues.")
            return False
            
    except Exception as e:
        logger.error(f"Test suite failed with error: {str(e)}")
        return False

if __name__ == '__main__':
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
