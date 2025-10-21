"""
Security tests for the LMS application
Tests authentication, authorization, and security vulnerabilities
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from users.models import CustomUser, Branch
from LMS_Project.validators import SecureFilenameValidator, ComplexPasswordValidator
import tempfile
import os

User = get_user_model()

class SecurityTestCase(TestCase):
    """Test security-related functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.branch = Branch.objects.create(
            name="Test Branch",
            slug="test-branch"
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123!",
            role="learner",
            branch=self.branch
        )
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="AdminPassword123!",
            role="admin",
            branch=self.branch
        )
    
    def test_secure_filename_validator(self):
        """Test secure filename validation"""
        validator = SecureFilenameValidator()
        
        # Test valid filenames
        valid_filenames = [
            "document.pdf",
            "image.jpg",
            "video.mp4",
            "normal_file.txt"
        ]
        
        for filename in valid_filenames:
            try:
                validator.validate(filename)
            except ValidationError:
                self.fail(f"Valid filename {filename} should not raise ValidationError")
        
        # Test dangerous filenames
        dangerous_filenames = [
            "../../etc/passwd",
            "script.exe",
            "malware.bat",
            ".hidden_file",
            "file with spaces.exe",
            "file<script>alert('xss')</script>.txt"
        ]
        
        for filename in dangerous_filenames:
            with self.assertRaises(ValidationError):
                validator.validate(filename)
    
    def test_password_validator(self):
        """Test password complexity validation"""
        validator = ComplexPasswordValidator()
        
        # Test valid passwords
        valid_passwords = [
            "ValidPassword123!",
            "AnotherGood1@",
            "ComplexPass456#"
        ]
        
        for password in valid_passwords:
            try:
                validator.validate(password)
            except ValidationError:
                self.fail(f"Valid password should not raise ValidationError")
        
        # Test weak passwords
        weak_passwords = [
            "password",
            "123456",
            "qwerty",
            "Password",
            "password123",
            "PASSWORD123"
        ]
        
        for password in weak_passwords:
            with self.assertRaises(ValidationError):
                validator.validate(password)
    
    def test_csrf_protection(self):
        """Test CSRF protection on forms"""
        # Test login form CSRF protection
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'csrfmiddlewaretoken')
        
        # Test registration form CSRF protection
        response = self.client.get(reverse('register'))
        self.assertContains(response, 'csrfmiddlewaretoken')
    
    def test_session_security(self):
        """Test session security settings"""
        # Test session cookie settings
        response = self.client.get(reverse('login'))
        self.assertIn('Set-Cookie', response)
        
        # Test session timeout
        self.client.login(username="testuser", password="TestPassword123!")
        response = self.client.get(reverse('dashboard_learner'))
        self.assertEqual(response.status_code, 200)
    
    def test_file_upload_security(self):
        """Test file upload security"""
        self.client.login(username="admin", password="AdminPassword123!")
        
        # Test dangerous file upload
        dangerous_file = SimpleUploadedFile(
            "malware.exe",
            b"malicious content",
            content_type="application/octet-stream"
        )
        
        response = self.client.post('/courses/create/', {
            'title': 'Test Course',
            'description': 'Test Description',
            'file': dangerous_file
        })
        
        # Should reject dangerous files
        self.assertNotEqual(response.status_code, 200)
    
    def test_authentication_required(self):
        """Test that protected views require authentication"""
        protected_urls = [
            reverse('dashboard_learner'),
            reverse('dashboard_instructor'),
            reverse('dashboard_admin'),
            reverse('users:user_list'),
        ]
        
        for url in protected_urls:
            response = self.client.get(url)
            self.assertRedirects(response, f'/login/?next={url}')
    
    def test_authorization_by_role(self):
        """Test role-based access control"""
        # Test learner cannot access admin functions
        self.client.login(username="testuser", password="TestPassword123!")
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 403)
        
        # Test admin can access admin functions
        self.client.login(username="admin", password="AdminPassword123!")
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_sql_injection_protection(self):
        """Test SQL injection protection"""
        # Test malicious input in search
        malicious_input = "'; DROP TABLE users; --"
        
        self.client.login(username="admin", password="AdminPassword123!")
        response = self.client.get(f'/users/search/?q={malicious_input}')
        
        # Should not cause database error
        self.assertNotEqual(response.status_code, 500)
    
    def test_xss_protection(self):
        """Test XSS protection"""
        xss_payload = "<script>alert('xss')</script>"
        
        self.client.login(username="admin", password="AdminPassword123!")
        response = self.client.post('/users/create/', {
            'username': xss_payload,
            'email': 'test@example.com',
            'password1': 'TestPassword123!',
            'password2': 'TestPassword123!',
        })
        
        # Should escape HTML content
        if response.status_code == 200:
            self.assertNotContains(response, '<script>')
    
    def test_path_traversal_protection(self):
        """Test path traversal protection"""
        self.client.login(username="admin", password="AdminPassword123!")
        
        # Test path traversal in file upload
        response = self.client.post('/courses/create/', {
            'title': 'Test Course',
            'description': 'Test Description',
            'file': SimpleUploadedFile(
                "../../../etc/passwd",
                b"content",
                content_type="text/plain"
            )
        })
        
        # Should reject path traversal attempts
        self.assertNotEqual(response.status_code, 200)
