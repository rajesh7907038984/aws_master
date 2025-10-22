"""
Comprehensive tests for gradebook type safety improvements.
"""

import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from courses.models import Course
from assignments.models import Assignment
from .models import Grade
from .validators import (
    validate_grade_score, validate_student_id, validate_activity_id,
    validate_activity_type, validate_grade_status, validate_feedback_text,
    validate_gradebook_request_data, GradebookValidationError,
    safe_grade_conversion
)

User = get_user_model()


class GradeModelTypesSafetyTestCase(TestCase):
    """Test type safety in Grade model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='student'
        )
        self.instructor = User.objects.create_user(
            username='instructor',
            email='instructor@example.com',
            password='testpass123',
            role='instructor'
        )
        self.course = Course.objects.create(
            title='Test Course',
            instructor=self.instructor
        )
        self.assignment = Assignment.objects.create(
            title='Test Assignment',
            course=self.course,
            max_score=100.00,
            user=self.instructor
        )
    
    def test_grade_model_validation_positive_score(self):
        """Test that positive scores are accepted."""
        grade = Grade(
            student=self.user,
            course=self.course,
            assignment=self.assignment,
            score=Decimal('85.50')
        )
        grade.full_clean()  # Should not raise
        grade.save()
        self.assertEqual(grade.score, Decimal('85.50'))
    
    def test_grade_model_validation_negative_score(self):
        """Test that negative scores are rejected."""
        grade = Grade(
            student=self.user,
            course=self.course,
            assignment=self.assignment,
            score=Decimal('-10.00')
        )
        with self.assertRaises(ValidationError) as cm:
            grade.full_clean()
        self.assertIn('Score cannot be negative', str(cm.exception))
    
    def test_grade_model_validation_excused_with_score(self):
        """Test that excused grades cannot have scores."""
        grade = Grade(
            student=self.user,
            course=self.course,
            assignment=self.assignment,
            score=Decimal('85.50'),
            excused=True
        )
        with self.assertRaises(ValidationError) as cm:
            grade.full_clean()
        self.assertIn('Excused grades should not have a score', str(cm.exception))
    
    def test_grade_model_validation_too_large_score(self):
        """Test that overly large scores are rejected."""
        grade = Grade(
            student=self.user,
            course=self.course,
            assignment=self.assignment,
            score=Decimal('10000.00')  # Exceeds max_digits=5, decimal_places=2
        )
        with self.assertRaises(ValidationError) as cm:
            grade.full_clean()
        self.assertIn('Score is too large', str(cm.exception))


class ValidatorTestCase(TestCase):
    """Test custom validators."""
    
    def test_validate_grade_score_valid_inputs(self):
        """Test valid grade score inputs."""
        # Test various valid formats
        self.assertEqual(validate_grade_score('85.5'), Decimal('85.5'))
        self.assertEqual(validate_grade_score(85.5), Decimal('85.5'))
        self.assertEqual(validate_grade_score(Decimal('85.5')), Decimal('85.5'))
        self.assertEqual(validate_grade_score('100'), Decimal('100'))
        self.assertEqual(validate_grade_score(0), Decimal('0'))
    
    def test_validate_grade_score_invalid_inputs(self):
        """Test invalid grade score inputs."""
        with self.assertRaises(ValidationError):
            validate_grade_score('invalid')
        
        with self.assertRaises(ValidationError):
            validate_grade_score('')
        
        with self.assertRaises(ValidationError):
            validate_grade_score(None)
        
        with self.assertRaises(ValidationError):
            validate_grade_score(-5)
        
        with self.assertRaises(ValidationError):
            validate_grade_score(10000)
    
    def test_validate_grade_score_with_max_score(self):
        """Test grade score validation with max score."""
        # Valid: score within max
        self.assertEqual(
            validate_grade_score('85', max_score=100),
            Decimal('85')
        )
        
        # Invalid: score exceeds max
        with self.assertRaises(ValidationError) as cm:
            validate_grade_score('105', max_score=100)
        self.assertIn('cannot exceed maximum score', str(cm.exception))
    
    def test_validate_student_id(self):
        """Test student ID validation."""
        self.assertEqual(validate_student_id('123'), 123)
        self.assertEqual(validate_student_id(123), 123)
        
        with self.assertRaises(ValidationError):
            validate_student_id('invalid')
        
        with self.assertRaises(ValidationError):
            validate_student_id(-1)
        
        with self.assertRaises(ValidationError):
            validate_student_id(0)
    
    def test_validate_activity_type(self):
        """Test activity type validation."""
        self.assertEqual(validate_activity_type('assignment'), 'assignment')
        self.assertEqual(validate_activity_type('QUIZ'), 'quiz')
        self.assertEqual(validate_activity_type(' Discussion '), 'discussion')
        
        with self.assertRaises(ValidationError):
            validate_activity_type('invalid_type')
        
        with self.assertRaises(ValidationError):
            validate_activity_type('')
        
        with self.assertRaises(ValidationError):
            validate_activity_type(123)
    
    def test_validate_grade_status(self):
        """Test grade status validation."""
        self.assertEqual(validate_grade_status('graded'), 'graded')
        self.assertEqual(validate_grade_status('NOT_GRADED'), 'not_graded')
        self.assertEqual(validate_grade_status(' Excused '), 'excused')
        
        with self.assertRaises(ValidationError):
            validate_grade_status('invalid_status')
        
        with self.assertRaises(ValidationError):
            validate_grade_status('')
    
    def test_validate_feedback_text(self):
        """Test feedback text validation."""
        self.assertEqual(validate_feedback_text('Good work!'), 'Good work!')
        self.assertEqual(validate_feedback_text('  '), '')
        self.assertEqual(validate_feedback_text(None), '')
        self.assertEqual(validate_feedback_text(123), '123')
        
        # Test length limit
        long_text = 'x' * 10001
        with self.assertRaises(ValidationError):
            validate_feedback_text(long_text)
    
    def test_validate_gradebook_request_data(self):
        """Test comprehensive request data validation."""
        valid_data = {
            'activity_type': 'assignment',
            'activity_id': '123',
            'student_id': '456',
            'grade': '85.5',
            'status': 'graded',
            'feedback': 'Good work!'
        }
        
        result = validate_gradebook_request_data(valid_data)
        
        self.assertEqual(result['activity_type'], 'assignment')
        self.assertEqual(result['activity_id'], 123)
        self.assertEqual(result['student_id'], 456)
        self.assertEqual(result['grade'], Decimal('85.5'))
        self.assertEqual(result['status'], 'graded')
        self.assertEqual(result['feedback'], 'Good work!')
    
    def test_validate_gradebook_request_data_missing_required(self):
        """Test validation with missing required fields."""
        invalid_data = {
            'activity_type': 'assignment',
            # Missing activity_id and student_id
        }
        
        with self.assertRaises(ValidationError) as cm:
            validate_gradebook_request_data(invalid_data)
        self.assertIn('Missing required field', str(cm.exception))
    
    def test_safe_grade_conversion(self):
        """Test safe grade conversion utility."""
        # Valid conversions
        self.assertEqual(safe_grade_conversion('85.5'), Decimal('85.5'))
        self.assertEqual(safe_grade_conversion(85), Decimal('85'))
        self.assertIsNone(safe_grade_conversion(''))
        self.assertIsNone(safe_grade_conversion(None))
        
        # Invalid conversion
        with self.assertRaises(GradebookValidationError):
            safe_grade_conversion('invalid')


class AjaxGradeSaveTypesSafetyTestCase(TestCase):
    """Test type safety in AJAX grade save endpoint."""
    
    def setUp(self):
        self.client = Client()
        self.instructor = User.objects.create_user(
            username='instructor',
            email='instructor@example.com',
            password='testpass123',
            role='instructor'
        )
        self.student = User.objects.create_user(
            username='student',
            email='student@example.com',
            password='testpass123',
            role='student'
        )
        self.course = Course.objects.create(
            title='Test Course',
            instructor=self.instructor
        )
        self.assignment = Assignment.objects.create(
            title='Test Assignment',
            course=self.course,
            max_score=100.00,
            user=self.instructor
        )
        
        # Login as instructor
        self.client.login(username='instructor', password='testpass123')
    
    def test_ajax_save_grade_valid_data(self):
        """Test AJAX grade save with valid data."""
        data = {
            'activity_type': 'assignment',
            'activity_id': str(self.assignment.id),
            'student_id': str(self.student.id),
            'grade': '85.5',
            'status': 'graded',
            'feedback': 'Good work!'
        }
        
        response = self.client.post(
            reverse('gradebook:ajax_save_grade'),
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data['success'])
    
    def test_ajax_save_grade_invalid_activity_type(self):
        """Test AJAX grade save with invalid activity type."""
        data = {
            'activity_type': 'invalid_type',
            'activity_id': str(self.assignment.id),
            'student_id': str(self.student.id),
            'grade': '85.5'
        }
        
        response = self.client.post(
            reverse('gradebook:ajax_save_grade'),
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('Invalid activity type', response_data['error'])
    
    def test_ajax_save_grade_invalid_grade_value(self):
        """Test AJAX grade save with invalid grade value."""
        data = {
            'activity_type': 'assignment',
            'activity_id': str(self.assignment.id),
            'student_id': str(self.student.id),
            'grade': 'invalid_grade'
        }
        
        response = self.client.post(
            reverse('gradebook:ajax_save_grade'),
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('must be a valid number', response_data['error'])
    
    def test_ajax_save_grade_missing_required_fields(self):
        """Test AJAX grade save with missing required fields."""
        data = {
            'activity_type': 'assignment',
            # Missing activity_id and student_id
        }
        
        response = self.client.post(
            reverse('gradebook:ajax_save_grade'),
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('Missing required field', response_data['error'])
    
    def test_ajax_save_grade_negative_score(self):
        """Test AJAX grade save with negative score."""
        data = {
            'activity_type': 'assignment',
            'activity_id': str(self.assignment.id),
            'student_id': str(self.student.id),
            'grade': '-10'
        }
        
        response = self.client.post(
            reverse('gradebook:ajax_save_grade'),
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('cannot be negative', response_data['error'])


class JavaScriptTypeSafetyTestCase(TestCase):
    """Test JavaScript type safety integration."""
    
    def test_type_safety_utils_loaded(self):
        """Test that type safety utilities are properly loaded."""
        # This would be tested in a browser environment
        # Here we just verify the file exists and has the right structure
        import os
        from django.conf import settings
        # Use dynamic path from settings instead of hardcoded path
        js_file = os.path.join(settings.BASE_DIR, 'static', 'js', 'type-safety-utils.js')
        self.assertTrue(os.path.exists(js_file))
        
        with open(js_file, 'r') as f:
            content = f.read()
            self.assertIn('window.LMS.TypeSafety', content)
            self.assertIn('safeJsonParse', content)
            self.assertIn('safeNumber', content)
            self.assertIn('validateFormData', content)


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    if not settings.configured:
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.base')
        django.setup()
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['gradebook.tests_type_safety'])
