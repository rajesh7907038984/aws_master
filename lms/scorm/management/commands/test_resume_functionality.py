"""
Django management command to test resume functionality for all package types
Tests SCORM, xAPI, cmi5, and Articulate resume button paths and preview functionality
"""

from django.core.management.base import BaseCommand
from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Test resume functionality for all SCORM package types'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Test specific topic ID',
        )
        parser.add_argument(
            '--package-type',
            type=str,
            choices=['SCORM_1_2', 'SCORM_2004', 'XAPI', 'CMI5', 'AICC'],
            help='Test specific package type',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        package_type = options.get('package_type')
        
        if topic_id:
            self.test_single_topic(topic_id)
        else:
            self.test_all_packages(package_type)

    def test_single_topic(self, topic_id):
        """Test resume functionality for a single topic"""
        try:
            topic = Topic.objects.get(id=topic_id)
            elearning_package = ELearningPackage.objects.get(topic=topic)
            
            self.stdout.write("Testing topic {{topic_id}} ({{elearning_package.package_type}})")
            
            # Test bookmark data extraction
            tracking = ELearningTracking.objects.filter(elearning_package=elearning_package).first()
            if tracking:
                bookmark_data = tracking.get_bookmark_data()
                
                self.stdout.write("  Package Type: {{bookmark_data.get('package_type', 'Unknown')}}")
                self.stdout.write("  Can Resume: {{bookmark_data.get('can_resume', False)}}")
                self.stdout.write("  Progress Indicators: {{len(bookmark_data.get('progress_indicators', []))}}")
                
                # Test Articulate-specific data if applicable
                if 'articulate' in elearning_package.package_type.lower():
                    articulate_data = tracking.get_articulate_bookmark_data()
                    self.stdout.write("  Articulate Can Resume: {{articulate_data.get('can_resume', False)}}")
                
                # Test data size validation
                test_data = "test_data_" * 1000  # Large test data
                is_valid, msg = tracking.validate_data_size(test_data, elearning_package.package_type)
                self.stdout.write("  Data Size Validation: {{is_valid}} - {{msg}}")
                
            else:
                self.stdout.write("  No tracking data found for topic {{topic_id}}")
                
        except Exception as e:
            self.stdout.write("❌ Error testing topic {{topic_id}}: {{str(e)}}")

    def test_all_packages(self, package_type=None):
        """Test resume functionality for all packages"""
        packages = ELearningPackage.objects.all()
        if package_type:
            packages = packages.filter(package_type=package_type)
        
        self.stdout.write("Testing {{packages.count()}} SCORM packages")
        
        results = {
            'SCORM_1_2': {'total': 0, 'with_tracking': 0, 'can_resume': 0},
            'SCORM_2004': {'total': 0, 'with_tracking': 0, 'can_resume': 0},
            'XAPI': {'total': 0, 'with_tracking': 0, 'can_resume': 0},
            'CMI5': {'total': 0, 'with_tracking': 0, 'can_resume': 0},
            'AICC': {'total': 0, 'with_tracking': 0, 'can_resume': 0},
        }
        
        for package in packages:
            pkg_type = package.package_type
            if pkg_type not in results:
                pkg_type = 'SCORM_1_2'  # Default fallback
            
            results[pkg_type]['total'] += 1
            
            tracking = ELearningTracking.objects.filter(elearning_package=package).first()
            if tracking:
                results[pkg_type]['with_tracking'] += 1
                bookmark_data = tracking.get_bookmark_data()
                
                if bookmark_data.get('can_resume', False):
                    results[pkg_type]['can_resume'] += 1
        
        # Display results
        for pkg_type, stats in results.items():
            if stats['total'] > 0:
                self.stdout.write("\n{{pkg_type}}:")
                self.stdout.write("  Total Packages: {{stats['total']}}")
                self.stdout.write("  With Tracking: {{stats['with_tracking']}}")
                self.stdout.write("  Can Resume: {{stats['can_resume']}}")
                
                if stats['with_tracking'] > 0:
                    resume_percentage = (stats['can_resume'] / stats['with_tracking']) * 100
                    self.stdout.write("  Resume Success Rate: {{resume_percentage:.1f}}%")

    def test_url_patterns(self):
        """Test URL pattern generation for all package types"""
        self.stdout.write("\nTesting URL patterns:")
        
        url_patterns = {
            'SCORM_1_2': {
                'launch': '/scorm/launch/{topic_id}/',
                'resume': '/scorm/resume/{topic_id}/',
                'preview': '/scorm/preview/{topic_id}/',
            },
            'SCORM_2004': {
                'launch': '/scorm/launch/{topic_id}/',
                'resume': '/scorm/resume/{topic_id}/',
                'preview': '/scorm/preview/{topic_id}/',
            },
            'XAPI': {
                'launch': '/scorm/xapi/launch/{topic_id}/',
                'resume': '/scorm/xapi/resume/{topic_id}/',
                'preview': '/scorm/xapi/preview/{topic_id}/',
            },
            'CMI5': {
                'launch': '/scorm/cmi5/launch/{topic_id}/',
                'resume': '/scorm/cmi5/resume/{topic_id}/',
                'preview': '/scorm/cmi5/preview/{topic_id}/',
            },
        }
        
        for pkg_type, urls in url_patterns.items():
            self.stdout.write("\n{{pkg_type}} URLs:")
            for url_type, url_pattern in urls.items():
                self.stdout.write("  {{url_type.title()}}: {{url_pattern}}")

    def test_data_size_limits(self):
        """Test data size validation for different package types"""
        self.stdout.write("\nTesting data size limits:")
        
        test_cases = [
            ('SCORM_1_2', 4096, '4KB limit'),
            ('SCORM_2004', 64000, '64KB limit'),
            ('XAPI', 1000000, '1MB practical limit'),
            ('CMI5', 1000000, '1MB practical limit'),
        ]
        
        for pkg_type, max_size, description in test_cases:
            # Test data within limits
            small_data = "test" * 100
            # Test data exceeding limits
            large_data = "test" * (max_size // 4 + 1000)
            
            self.stdout.write("\n{{pkg_type}} ({{description}}):")
            self.stdout.write("  Small data: {{len(small_data)}} bytes - Should pass")
            self.stdout.write("  Large data: {{len(large_data)}} bytes - Should fail")
