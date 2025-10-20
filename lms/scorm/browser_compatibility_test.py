#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Browser Compatibility Test for SCORM Implementation
Tests all browser compatibility fixes and optimizations
"""

import os
import sys
import django
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch, MagicMock

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
django.setup()

from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course

User = get_user_model()

class BrowserCompatibilityTest(TestCase):
    """Test browser compatibility features"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.course = Course.objects.create(
            title='Test Course',
            description='Test course for browser compatibility',
            instructor=self.user
        )
        
        self.topic = Topic.objects.create(
            title='Test SCORM Topic',
            description='Test SCORM topic for browser compatibility',
            course=self.course,
            created_by=self.user
        )
        
        self.elearning_package = ELearningPackage.objects.create(
            topic=self.topic,
            package_type='SCORM_1_2',
            title='Test SCORM Package',
            is_extracted=True,
            extracted_path='/test/path',
            launch_file='index.html'
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_mobile_device_detection(self):
        """Test mobile device detection"""
        from scorm.views import is_mobile_device, get_browser_info
        
        # Test mobile user agents
        mobile_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
            'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36',
            'Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
            'Mozilla/5.0 (BlackBerry; U; BlackBerry 9800; en) AppleWebKit/534.1+',
            'Mozilla/5.0 (Windows Phone 10.0; Android 4.2.1; Microsoft; Lumia 950) AppleWebKit/537.36'
        ]
        
        for agent in mobile_agents:
            request = MagicMock()
            request.META = {'HTTP_USER_AGENT': agent}
            self.assertTrue(is_mobile_device(request), "Failed to detect mobile: {}".format(agent))
        
        # Test desktop user agents
        desktop_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        
        for agent in desktop_agents:
            request = MagicMock()
            request.META = {'HTTP_USER_AGENT': agent}
            self.assertFalse(is_mobile_device(request), "False positive for mobile: {}".format(agent))
    
    def test_browser_info_detection(self):
        """Test browser information detection"""
        from scorm.views import get_browser_info
        
        # Test Chrome detection
        request = MagicMock()
        request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        browser_info = get_browser_info(request)
        
        self.assertTrue(browser_info['is_chrome'])
        self.assertFalse(browser_info['is_firefox'])
        self.assertFalse(browser_info['is_safari'])
        self.assertFalse(browser_info['is_ie'])
        self.assertFalse(browser_info['is_mobile'])
        self.assertTrue(browser_info['supports_es6'])
        self.assertTrue(browser_info['supports_postmessage'])
        
        # Test Firefox detection
        request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'}
        browser_info = get_browser_info(request)
        
        self.assertFalse(browser_info['is_chrome'])
        self.assertTrue(browser_info['is_firefox'])
        self.assertFalse(browser_info['is_safari'])
        self.assertFalse(browser_info['is_ie'])
        self.assertFalse(browser_info['is_mobile'])
        
        # Test Internet Explorer detection
        request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; AS; rv:11.0) like Gecko'}
        browser_info = get_browser_info(request)
        
        self.assertFalse(browser_info['is_chrome'])
        self.assertFalse(browser_info['is_firefox'])
        self.assertFalse(browser_info['is_safari'])
        self.assertTrue(browser_info['is_ie'])
        self.assertFalse(browser_info['is_mobile'])
        self.assertFalse(browser_info['supports_es6'])
    
    def test_mobile_template_selection(self):
        """Test mobile template selection"""
        # Test mobile request
        mobile_request = MagicMock()
        mobile_request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'}
        mobile_request.user = self.user
        mobile_request.session = {'_auth_user_id': self.user.id}
        
        with patch('scorm.views.render') as mock_render:
            from scorm.views import scorm_launch
            scorm_launch(mobile_request, self.topic.id)
            
            # Check if mobile template was used
            call_args = mock_render.call_args
            self.assertEqual(call_args[0][1], 'scorm/mobile_launch.html')
    
    def test_desktop_template_selection(self):
        """Test desktop template selection"""
        # Test desktop request
        desktop_request = MagicMock()
        desktop_request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        desktop_request.user = self.user
        desktop_request.session = {'_auth_user_id': self.user.id}
        
        with patch('scorm.views.render') as mock_render:
            from scorm.views import scorm_launch
            scorm_launch(desktop_request, self.topic.id)
            
            # Check if desktop template was used
            call_args = mock_render.call_args
            self.assertEqual(call_args[0][1], 'scorm/launch.html')
    
    def test_error_fixes_endpoint(self):
        """Test error fixes JavaScript endpoint"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        
        # Check if JavaScript contains browser compatibility fixes
        content = response.content.decode('utf-8')
        self.assertIn('browserInfo', content)
        self.assertIn('isIE', content)
        self.assertIn('isMobile', content)
        self.assertIn('fixIECompatibility', content)
        self.assertIn('fixMobileTouchEvents', content)
        self.assertIn('fixVideoControls', content)
    
    def test_console_cleaner_endpoint(self):
        """Test console cleaner JavaScript endpoint"""
        response = self.client.get(reverse('scorm:console_cleaner'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        
        # Check if JavaScript contains console cleaning features
        content = response.content.decode('utf-8')
        self.assertIn('shouldFilterError', content)
        self.assertIn('shouldFilterWarning', content)
        self.assertIn('minimal-ui', content)
        self.assertIn('analytics', content)
    
    def test_scorm_launch_with_browser_info(self):
        """Test SCORM launch with browser information"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        # Check if browser info is in context
        self.assertIn('browser_info', response.context)
        self.assertIn('is_mobile', response.context)
        
        browser_info = response.context['browser_info']
        self.assertIn('is_mobile', browser_info)
        self.assertIn('is_ie', browser_info)
        self.assertIn('is_chrome', browser_info)
        self.assertIn('is_firefox', browser_info)
        self.assertIn('is_safari', browser_info)
        self.assertIn('supports_es6', browser_info)
        self.assertIn('supports_postmessage', browser_info)
        self.assertIn('supports_touch', browser_info)
    
    def test_mobile_launch_template(self):
        """Test mobile launch template exists and is accessible"""
        # Create a mobile request
        mobile_request = MagicMock()
        mobile_request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'}
        mobile_request.user = self.user
        mobile_request.session = {'_auth_user_id': self.user.id}
        
        with patch('scorm.views.render') as mock_render:
            from scorm.views import scorm_launch
            scorm_launch(mobile_request, self.topic.id)
            
            # Check if mobile template was selected
            call_args = mock_render.call_args
            self.assertEqual(call_args[0][1], 'scorm/mobile_launch.html')
    
    def test_iframe_attributes(self):
        """Test iframe attributes for browser compatibility"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        # Check if iframe has proper attributes
        content = response.content.decode('utf-8')
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-presentation allow-top-navigation allow-downloads allow-modals"', content)
        self.assertIn('allow="fullscreen; microphone; camera; autoplay; encrypted-media; picture-in-picture; web-share; accelerometer; gyroscope; clipboard-write; clipboard-read; payment; usb; bluetooth"', content)
        self.assertIn('referrerpolicy="strict-origin-when-cross-origin"', content)
        self.assertIn('loading="eager"', content)
    
    def test_mobile_meta_tags(self):
        """Test mobile meta tags"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('name="viewport"', content)
        self.assertIn('name="mobile-web-app-capable"', content)
        self.assertIn('name="apple-mobile-web-app-capable"', content)
        self.assertIn('name="format-detection"', content)
    
    def test_video_controls_css(self):
        """Test video controls CSS for browser compatibility"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('video::-webkit-media-controls', content)
        self.assertIn('video::-webkit-media-controls-panel', content)
        self.assertIn('video::-webkit-media-controls-timeline', content)
        self.assertIn('video::-webkit-media-controls-play-button', content)
        self.assertIn('video::-webkit-media-controls-mute-button', content)
        self.assertIn('video::-webkit-media-controls-fullscreen-button', content)
    
    def test_cross_origin_communication(self):
        """Test cross-origin communication setup"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('addEventListener(\'message\'', content)
        self.assertIn('SCORM_API_READY', content)
        self.assertIn('postMessage', content)
    
    def test_ie_compatibility_polyfills(self):
        """Test Internet Explorer compatibility polyfills"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('Array.prototype.includes', content)
        self.assertIn('String.prototype.includes', content)
        self.assertIn('fixIECompatibility', content)
    
    def test_mobile_touch_events(self):
        """Test mobile touch event handling"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('fixMobileTouchEvents', content)
        self.assertIn('touchend', content)
        self.assertIn('touchAction', content)
        self.assertIn('manipulation', content)
    
    def test_analytics_blocking(self):
        """Test analytics blocking"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('analytics', content)
        self.assertIn('fixAnalytics', content)
        self.assertIn('XMLHttpRequest', content)
    
    def test_source_map_error_suppression(self):
        """Test source map error suppression"""
        response = self.client.get(reverse('scorm:console_cleaner'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('.map', content)
        self.assertIn('404', content)
        self.assertIn('Source Map', content)
        self.assertIn('shouldFilterError', content)
    
    def test_viewport_warning_suppression(self):
        """Test viewport warning suppression"""
        response = self.client.get(reverse('scorm:console_cleaner'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('minimal-ui', content)
        self.assertIn('viewport', content)
        self.assertIn('shouldFilterWarning', content)
    
    def test_browser_specific_headers(self):
        """Test browser-specific headers in SCORM API"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('X-Browser', content)
        self.assertIn('Chrome', content)
        self.assertIn('Firefox', content)
        self.assertIn('Safari', content)
        self.assertIn('Edge', content)
        self.assertIn('IE', content)
    
    def test_mobile_specific_features(self):
        """Test mobile-specific features"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('isMobile', content)
        self.assertIn('touchEnabled', content)
        self.assertIn('orientation', content)
        self.assertIn('visibilitychange', content)
    
    def test_performance_optimizations(self):
        """Test performance optimizations"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('loading="eager"', content)
        self.assertIn('display: block', content)
        self.assertIn('background: white', content)
    
    def test_security_enhancements(self):
        """Test security enhancements"""
        response = self.client.get(reverse('scorm:launch', args=[self.topic.id]))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('sandbox=', content)
        self.assertIn('allow=', content)
        self.assertIn('referrerpolicy=', content)
        self.assertIn('strict-origin-when-cross-origin', content)
    
    def test_error_recovery_system(self):
        """Test error recovery system"""
        response = self.client.get(reverse('scorm:error_fixes'))
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('try {', content)
        self.assertIn('catch (', content)
        self.assertIn('fallback', content)
        self.assertIn('error', content)
    
    def test_comprehensive_browser_support(self):
        """Test comprehensive browser support"""
        browsers = [
            'Chrome/91.0.4472.124',
            'Firefox/89.0',
            'Safari/605.1.15',
            'Edge/91.0.864.59',
            'MSIE 11.0',
            'Trident/7.0',
            'Mobile Safari/605.1.15',
            'Chrome Mobile/91.0.4472.124'
        ]
        
        for browser in browsers:
            request = MagicMock()
            request.META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) {}'.format(browser)}
            request.user = self.user
            request.session = {'_auth_user_id': self.user.id}
            
            with patch('scorm.views.render') as mock_render:
                from scorm.views import scorm_launch
                scorm_launch(request, self.topic.id)
                
                # Should not raise any exceptions
                self.assertTrue(True, "Failed for browser: {}".format(browser))

def run_browser_compatibility_tests():
    """Run all browser compatibility tests"""
    print("🧪 Running Browser Compatibility Tests...")
    
    # Create test suite
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(BrowserCompatibilityTest)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print results
    if result.wasSuccessful():
        print("\n✅ All Browser Compatibility Tests Passed!")
        print("📊 Tests Run: {}".format(result.testsRun))
        print("⏱️  Time: {:.2f}s".format(result.time))
    else:
        print("\n❌ Some Browser Compatibility Tests Failed!")
        print("📊 Tests Run: {}".format(result.testsRun))
        print("❌ Failures: {}".format(len(result.failures)))
        print("❌ Errors: {}".format(len(result.errors)))
        
        for failure in result.failures:
            print("\n❌ Failure: {}".format(failure[0]))
            print("   {}".format(failure[1]))
        
        for error in result.errors:
            print("\n❌ Error: {}".format(error[0]))
            print("   {}".format(error[1]))
    
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_browser_compatibility_tests()
    sys.exit(0 if success else 1)
