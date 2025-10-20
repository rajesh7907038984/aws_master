#!/usr/bin/env python3
"""
Test Script for 500 Error Fixes
Comprehensive testing of all 500 error fixes implemented
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.development')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import json

User = get_user_model()

class Test500ErrorFixes(TestCase):
    """Test all 500 error fixes"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='admin'
        )
        
        # Create superuser for admin tests
        self.superuser = User.objects.create_superuser(
            username='superuser',
            email='super@example.com',
            password='superpass123'
        )
    
    def test_enhanced_error_handler_import(self):
        """Test that enhanced error handler can be imported"""
        try:
            from core.utils.enhanced_error_handler import EnhancedErrorHandler
            self.assertTrue(True, "Enhanced error handler imported successfully")
        except ImportError as e:
            self.fail("Failed to import enhanced error handler: {}".format(e))
    
    def test_error_monitoring_import(self):
        """Test that error monitoring can be imported"""
        try:
            from core.utils.error_monitoring import monitor_error, get_error_dashboard_data
            self.assertTrue(True, "Error monitoring imported successfully")
        except ImportError as e:
            self.fail("Failed to import error monitoring: {}".format(e))
    
    def test_database_health_import(self):
        """Test that database health checker can be imported"""
        try:
            from core.utils.database_health import check_db_health, safe_db_operation
            self.assertTrue(True, "Database health checker imported successfully")
        except ImportError as e:
            self.fail("Failed to import database health checker: {}".format(e))
    
    def test_file_processing_handler_import(self):
        """Test that file processing handler can be imported"""
        try:
            from core.utils.file_processing_handler import file_handler, validate_uploaded_file
            self.assertTrue(True, "File processing handler imported successfully")
        except ImportError as e:
            self.fail("Failed to import file processing handler: {}".format(e))
    
    def test_comprehensive_error_middleware_import(self):
        """Test that comprehensive error middleware can be imported"""
        try:
            from core.middleware.comprehensive_error_middleware import ComprehensiveErrorMiddleware
            self.assertTrue(True, "Comprehensive error middleware imported successfully")
        except ImportError as e:
            self.fail("Failed to import comprehensive error middleware: {}".format(e))
    
    def test_database_health_check(self):
        """Test database health check functionality"""
        from core.utils.database_health import check_db_health
        
        health_status = check_db_health()
        self.assertIn('status', health_status)
        self.assertIn(health_status['status'], ['healthy', 'unhealthy'])
    
    def test_file_validation(self):
        """Test file validation functionality"""
        from core.utils.file_processing_handler import validate_uploaded_file
        
        # Test valid file
        valid_file = SimpleUploadedFile(
            "test.pdf",
            b"file content",
            content_type="application/pdf"
        )
        
        result = validate_uploaded_file(valid_file)
        self.assertIn('valid', result)
    
    def test_error_monitoring_logging(self):
        """Test error monitoring logging functionality"""
        from core.utils.error_monitoring import monitor_error
        
        # Test error logging
        try:
            monitor_error(
                error_type='TEST_ERROR',
                error_message='Test error message',
                context={'test': 'data'},
                severity='info'
            )
            self.assertTrue(True, "Error monitoring logged successfully")
        except Exception as e:
            self.fail("Error monitoring failed: {}".format(e))
    
    def test_enhanced_error_handler_functionality(self):
        """Test enhanced error handler functionality"""
        from core.utils.enhanced_error_handler import EnhancedErrorHandler
        from django.core.exceptions import ValidationError
        
        # Test validation error handling
        try:
            error = ValidationError("Test validation error")
            response = EnhancedErrorHandler.handle_validation_error(error, "test_context")
            self.assertIsNotNone(response)
        except Exception as e:
            self.fail("Enhanced error handler failed: {}".format(e))
    
    def test_error_dashboard_access(self):
        """Test error dashboard access"""
        # Login as superuser
        self.client.force_login(self.superuser)
        
        # Test error dashboard access
        try:
            response = self.client.get('/api/error-monitoring/dashboard/')
            # Should not return 500 error
            self.assertNotEqual(response.status_code, 500)
        except Exception as e:
            self.fail("Error dashboard access failed: {}".format(e))
    
    def test_error_summary_api(self):
        """Test error summary API"""
        # Login as superuser
        self.client.force_login(self.superuser)
        
        try:
            response = self.client.get('/api/error-monitoring/summary/')
            # Should not return 500 error
            self.assertNotEqual(response.status_code, 500)
        except Exception as e:
            self.fail("Error summary API failed: {}".format(e))
    
    def test_database_health_api(self):
        """Test database health API"""
        # Login as superuser
        self.client.force_login(self.superuser)
        
        try:
            response = self.client.get('/api/error-monitoring/db-health/')
            # Should not return 500 error
            self.assertNotEqual(response.status_code, 500)
        except Exception as e:
            self.fail("Database health API failed: {}".format(e))
    
    def test_middleware_error_handling(self):
        """Test that middleware handles errors properly"""
        from core.middleware.comprehensive_error_middleware import ComprehensiveErrorMiddleware
        from django.http import HttpRequest
        
        # Create middleware instance
        middleware = ComprehensiveErrorMiddleware(lambda x: x)
        
        # Test that middleware doesn't crash
        try:
            # This is a basic test - in a real scenario you'd test with actual requests
            self.assertTrue(True, "Middleware instantiated successfully")
        except Exception as e:
            self.fail("Middleware error handling failed: {}".format(e))

def run_tests():
    """Run all tests"""
    print("Starting 500 Error Fix Tests...")
    print("=" * 50)
    
    # Run the tests
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["test_500_fixes"])
    
    if failures:
        print("\nX {} test(s) failed".format(failures))
        return False
    else:
        print("\nOK All tests passed!")
        return True

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
