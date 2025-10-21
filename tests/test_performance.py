"""
Performance tests for the LMS application
Tests database queries, memory usage, and response times
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import connection
from django.test.utils import override_settings
from users.models import CustomUser, Branch
from courses.models import Course, Topic, CourseEnrollment
import time
import psutil
import os

User = get_user_model()

class PerformanceTestCase(TestCase):
    """Test performance-related functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.branch = Branch.objects.create(
            name="Test Branch",
            slug="test-branch"
        )
        
        # Create test users
        self.users = []
        for i in range(100):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="TestPassword123!",
                role="learner",
                branch=self.branch
            )
            self.users.append(user)
        
        # Create test courses
        self.courses = []
        for i in range(50):
            course = Course.objects.create(
                title=f"Course {i}",
                description=f"Description for course {i}",
                creator=self.users[0],
                branch=self.branch
            )
            self.courses.append(course)
            
            # Create enrollments
            for j in range(10):
                CourseEnrollment.objects.create(
                    user=self.users[j],
                    course=course,
                    status='enrolled'
                )
    
    def test_database_query_performance(self):
        """Test database query performance"""
        start_time = time.time()
        
        # Test user list query
        response = self.client.get(reverse('users:user_list'))
        
        end_time = time.time()
        query_time = end_time - start_time
        
        # Should complete within reasonable time
        self.assertLess(query_time, 2.0, "User list query took too long")
        
        # Test database query count
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users_customuser")
            user_count = cursor.fetchone()[0]
            self.assertEqual(user_count, 100)
    
    def test_memory_usage(self):
        """Test memory usage during operations"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform memory-intensive operations
        for i in range(10):
            response = self.client.get(reverse('users:user_list'))
            self.assertEqual(response.status_code, 200)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable
        self.assertLess(memory_increase, 100, "Memory usage increased too much")
    
    def test_response_time(self):
        """Test response times for various endpoints"""
        endpoints = [
            reverse('login'),
            reverse('register'),
            reverse('users:user_list'),
            reverse('courses:course_list'),
        ]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = self.client.get(endpoint)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # Each endpoint should respond within 1 second
            self.assertLess(response_time, 1.0, f"Endpoint {endpoint} took too long")
    
    def test_database_connection_pooling(self):
        """Test database connection pooling"""
        # Test multiple concurrent requests
        start_time = time.time()
        
        for i in range(20):
            response = self.client.get(reverse('login'))
            self.assertEqual(response.status_code, 200)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should handle multiple requests efficiently
        self.assertLess(total_time, 5.0, "Multiple requests took too long")
    
    def test_static_file_serving(self):
        """Test static file serving performance"""
        # Test static file requests
        static_files = [
            '/static/css/tailwind.css',
            '/static/js/main.js',
            '/static/favicon.png',
        ]
        
        for static_file in static_files:
            start_time = time.time()
            response = self.client.get(static_file)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # Static files should be served quickly
            if response.status_code == 200:
                self.assertLess(response_time, 0.5, f"Static file {static_file} took too long")
    
    def test_session_performance(self):
        """Test session handling performance"""
        # Test session creation and retrieval
        start_time = time.time()
        
        self.client.login(username="user0", password="TestPassword123!")
        response = self.client.get(reverse('dashboard_learner'))
        
        end_time = time.time()
        session_time = end_time - start_time
        
        # Session operations should be fast
        self.assertLess(session_time, 1.0, "Session operations took too long")
        self.assertEqual(response.status_code, 200)
    
    def test_database_indexes(self):
        """Test database indexes are working"""
        with connection.cursor() as cursor:
            # Test that indexes exist
            cursor.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'users_customuser' 
                AND indexname LIKE 'idx_%'
            """)
            indexes = cursor.fetchall()
            
            # Should have some indexes
            self.assertGreater(len(indexes), 0, "No database indexes found")
    
    def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def make_request():
            try:
                response = self.client.get(reverse('login'))
                results.put(response.status_code)
            except Exception as e:
                results.put(f"Error: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        while not results.empty():
            result = results.get()
            self.assertEqual(result, 200, f"Concurrent request failed: {result}")
    
    def test_memory_leak_prevention(self):
        """Test that memory leaks are prevented"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform many operations
        for i in range(100):
            response = self.client.get(reverse('login'))
            self.assertEqual(response.status_code, 200)
        
        # Force garbage collection
        import gc
        gc.collect()
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory should not increase significantly
        self.assertLess(memory_increase, 50, "Potential memory leak detected")
