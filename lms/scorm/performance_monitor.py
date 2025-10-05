#!/usr/bin/env python3
"""
SCORM Performance Monitor
Monitors SCORM content loading performance and provides optimization recommendations
"""

import time
import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from scorm.models import ScormPackage, ScormAttempt

logger = logging.getLogger(__name__)

class SCORMPerformanceMonitor:
    """Monitor SCORM performance and provide optimization recommendations"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'BASE_URL', 'https://staging.nexsy.io')
        self.performance_data = []
    
    def test_scorm_loading_speed(self, topic_id):
        """Test SCORM content loading speed for a specific topic"""
        try:
            # Test SCORM view endpoint
            start_time = time.time()
            response = requests.get(f"{self.base_url}/scorm/view/{topic_id}/", timeout=30)
            load_time = time.time() - start_time
            
            if response.status_code == 200:
                logger.info(f"✅ SCORM view loaded in {load_time:.2f}s for topic {topic_id}")
                return {
                    'topic_id': topic_id,
                    'load_time': load_time,
                    'status': 'success',
                    'status_code': response.status_code
                }
            else:
                logger.error(f"❌ SCORM view failed with status {response.status_code}")
                return {
                    'topic_id': topic_id,
                    'load_time': load_time,
                    'status': 'error',
                    'status_code': response.status_code
                }
        except Exception as e:
            logger.error(f"❌ Error testing SCORM loading: {str(e)}")
            return {
                'topic_id': topic_id,
                'load_time': None,
                'status': 'error',
                'error': str(e)
            }
    
    def test_scorm_content_serving(self, topic_id, content_path='index.html'):
        """Test SCORM content serving speed"""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/scorm/content/{topic_id}/{content_path}", timeout=30)
            load_time = time.time() - start_time
            
            if response.status_code == 200:
                logger.info(f"✅ SCORM content served in {load_time:.2f}s for {content_path}")
                return {
                    'topic_id': topic_id,
                    'content_path': content_path,
                    'load_time': load_time,
                    'status': 'success',
                    'content_size': len(response.content)
                }
            else:
                logger.error(f"❌ SCORM content failed with status {response.status_code}")
                return {
                    'topic_id': topic_id,
                    'content_path': content_path,
                    'load_time': load_time,
                    'status': 'error',
                    'status_code': response.status_code
                }
        except Exception as e:
            logger.error(f"❌ Error testing SCORM content: {str(e)}")
            return {
                'topic_id': topic_id,
                'content_path': content_path,
                'load_time': None,
                'status': 'error',
                'error': str(e)
            }
    
    def analyze_performance(self):
        """Analyze performance data and provide recommendations"""
        if not self.performance_data:
            return "No performance data available"
        
        successful_tests = [test for test in self.performance_data if test.get('status') == 'success']
        
        if not successful_tests:
            return "No successful tests to analyze"
        
        avg_load_time = sum(test['load_time'] for test in successful_tests) / len(successful_tests)
        
        recommendations = []
        
        if avg_load_time > 5.0:
            recommendations.append("🔴 CRITICAL: Average load time is over 5 seconds")
            recommendations.append("   - Enable CloudFront CDN for S3 content")
            recommendations.append("   - Implement aggressive caching")
            recommendations.append("   - Optimize SCORM package size")
        elif avg_load_time > 3.0:
            recommendations.append("🟡 WARNING: Average load time is over 3 seconds")
            recommendations.append("   - Consider enabling CloudFront CDN")
            recommendations.append("   - Increase cache duration")
        else:
            recommendations.append("🟢 GOOD: Average load time is under 3 seconds")
        
        # Check for specific issues
        slow_tests = [test for test in successful_tests if test['load_time'] > 5.0]
        if slow_tests:
            recommendations.append(f"⚠️  {len(slow_tests)} tests took over 5 seconds")
        
        return {
            'average_load_time': avg_load_time,
            'total_tests': len(self.performance_data),
            'successful_tests': len(successful_tests),
            'recommendations': recommendations
        }
    
    def run_performance_test(self, topic_ids=None):
        """Run comprehensive performance tests"""
        if not topic_ids:
            # Get all topics with SCORM packages
            scorm_topics = ScormPackage.objects.select_related('topic').all()[:5]  # Limit to 5 for testing
            topic_ids = [pkg.topic.id for pkg in scorm_topics]
        
        logger.info(f"🚀 Starting SCORM performance test for {len(topic_ids)} topics")
        
        for topic_id in topic_ids:
            logger.info(f"Testing topic {topic_id}...")
            
            # Test SCORM view
            view_result = self.test_scorm_loading_speed(topic_id)
            self.performance_data.append(view_result)
            
            # Test SCORM content serving
            content_result = self.test_scorm_content_serving(topic_id)
            self.performance_data.append(content_result)
            
            # Small delay between tests
            time.sleep(1)
        
        # Analyze results
        analysis = self.analyze_performance()
        return analysis

def run_scorm_performance_test():
    """Run SCORM performance test"""
    monitor = SCORMPerformanceMonitor()
    results = monitor.run_performance_test()
    
    print("\n" + "="*60)
    print("SCORM PERFORMANCE TEST RESULTS")
    print("="*60)
    
    if isinstance(results, dict):
        print(f"Average Load Time: {results['average_load_time']:.2f}s")
        print(f"Total Tests: {results['total_tests']}")
        print(f"Successful Tests: {results['successful_tests']}")
        print("\nRecommendations:")
        for rec in results['recommendations']:
            print(f"  {rec}")
    else:
        print(results)
    
    print("="*60)
    
    return results

if __name__ == "__main__":
    run_scorm_performance_test()
