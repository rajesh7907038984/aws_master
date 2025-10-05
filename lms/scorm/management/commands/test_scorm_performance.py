from django.core.management.base import BaseCommand
from scorm.performance_monitor import run_scorm_performance_test

class Command(BaseCommand):
    help = 'Test SCORM content loading performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-ids',
            nargs='+',
            type=int,
            help='Specific topic IDs to test (optional)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting SCORM performance test...'))
        
        try:
            from scorm.performance_monitor import SCORMPerformanceMonitor
            
            monitor = SCORMPerformanceMonitor()
            topic_ids = options.get('topic_ids')
            
            results = monitor.run_performance_test(topic_ids)
            
            self.stdout.write(self.style.SUCCESS('Performance test completed!'))
            
            if isinstance(results, dict):
                self.stdout.write(f"Average Load Time: {results['average_load_time']:.2f}s")
                self.stdout.write(f"Total Tests: {results['total_tests']}")
                self.stdout.write(f"Successful Tests: {results['successful_tests']}")
                
                self.stdout.write("\nRecommendations:")
                for rec in results['recommendations']:
                    self.stdout.write(f"  {rec}")
            else:
                self.stdout.write(results)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error running performance test: {str(e)}'))
