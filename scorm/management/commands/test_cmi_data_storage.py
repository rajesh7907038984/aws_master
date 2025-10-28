"""
Management command to test complete CMI data storage
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from scorm.cmi_data_handler import CMIDataHandler
from scorm.enhanced_scorm_api_handler import EnhancedScormAPIHandler

User = get_user_model()


class Command(BaseCommand):
    help = 'Test complete CMI data storage functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            default='learner3_branch1_test',
            help='Username to test with'
        )
        parser.add_argument(
            '--topic',
            type=int,
            default=125,
            help='Topic ID to test with'
        )

    def handle(self, *args, **options):
        username = options['user']
        topic_id = options['topic']

        self.stdout.write(f'Testing CMI data storage for user: {username}, topic: {topic_id}')

        try:
            # Get user and attempt
            user = User.objects.get(username=username)
            attempt = ScormAttempt.objects.filter(user=user, scorm_package__topic_id=topic_id).first()

            if not attempt:
                self.stdout.write(self.style.ERROR(f'No SCORM attempt found for user {username} and topic {topic_id}'))
                return

            self.stdout.write(f'Found attempt: {attempt.id}')

            # Test CMI Data Handler
            self.stdout.write('\n=== Testing CMI Data Handler ===')
            cmi_handler = CMIDataHandler(attempt)

            # Test field updates
            test_fields = [
                ('cmi.score.raw', '85'),
                ('cmi.score.min', '0'),
                ('cmi.score.max', '100'),
                ('cmi.completion_status', 'completed'),
                ('cmi.success_status', 'passed'),
                ('cmi.core.lesson_status', 'completed'),
                ('cmi.core.total_time', '0000:05:30.00'),
                ('cmi.core.lesson_location', 'slide_5'),
            ]

            for field, value in test_fields:
                success = cmi_handler.update_cmi_field(field, value)
                if success:
                    self.stdout.write(self.style.SUCCESS(f'✓ Updated {field} = {value}'))
                else:
                    self.stdout.write(self.style.ERROR(f'✗ Failed to update {field} = {value}'))

            # Test Enhanced SCORM API Handler
            self.stdout.write('\n=== Testing Enhanced SCORM API Handler ===')
            api_handler = EnhancedScormAPIHandler(attempt)

            # Test API methods
            self.stdout.write('Testing GetValue...')
            score_raw = api_handler.get_value('cmi.score.raw')
            self.stdout.write(f'cmi.score.raw = "{score_raw}"')

            self.stdout.write('Testing SetValue...')
            result = api_handler.set_value('cmi.score.raw', '90')
            self.stdout.write(f'SetValue result: {result}')

            self.stdout.write('Testing Commit...')
            commit_result = api_handler.commit()
            self.stdout.write(f'Commit result: {commit_result}')

            # Test CMI data summary
            self.stdout.write('\n=== CMI Data Summary ===')
            summary = api_handler.get_cmi_data_summary()
            self.stdout.write(f'Total CMI fields: {summary["total_cmi_fields"]}')
            self.stdout.write(f'CMI history entries: {summary["cmi_history_entries"]}')
            self.stdout.write(f'Score fields: {summary["score_fields"]}')
            self.stdout.write(f'Status fields: {summary["status_fields"]}')

            # Test validation
            self.stdout.write('\n=== CMI Data Validation ===')
            validation_results = api_handler.validate_cmi_data()
            valid_count = sum(1 for result in validation_results.values() if result['valid'])
            total_count = len(validation_results)
            self.stdout.write(f'Valid fields: {valid_count}/{total_count}')

            # Test export
            self.stdout.write('\n=== CMI Data Export ===')
            export_data = api_handler.export_complete_cmi_data()
            self.stdout.write(f'Export contains {len(export_data["cmi_data"])} CMI fields')
            self.stdout.write(f'Export contains {len(export_data["cmi_history"])} history entries')

            # Show CMI history
            self.stdout.write('\n=== CMI History ===')
            history = cmi_handler.get_cmi_history()
            for entry in history[-5:]:  # Show last 5 entries
                self.stdout.write(f'{entry["timestamp"]}: {entry["field"]} = {entry["new_value"]}')

            self.stdout.write(self.style.SUCCESS('\n✓ CMI data storage test completed successfully!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during test: {str(e)}'))
            import traceback
            traceback.print_exc()
