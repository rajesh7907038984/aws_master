from django.core.management.base import BaseCommand
from courses.models import *
from scorm_cloud.models import *
from django.db import transaction

class Command(BaseCommand):
    help = 'Cleans all course-related data from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not options['force']:
            confirm = input('This will delete ALL course data. Are you sure? [y/N]: ')
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return

        with transaction.atomic():
            # Clean SCORM related data
            self.stdout.write('Cleaning SCORM data...')
            try:
                # Use new SCORM implementation - clean TopicProgress instead
                from courses.models import TopicProgress
                TopicProgress.objects.all().delete()
                self.stdout.write('Cleaned TopicProgress data (new SCORM implementation)')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cleaning SCORM data: {str(e)}'))

            # Clean Assessment related data
            self.stdout.write('Cleaning assessment data...')
            try:
                AssignmentSubmission.objects.all().delete()
                Assignment.objects.all().delete()
                QuestionResponse.objects.all().delete()
                Question.objects.all().delete()
                Quiz.objects.all().delete()
                CourseAssessment.objects.all().delete()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cleaning assessment data: {str(e)}'))

            # Clean Course related data
            self.stdout.write('Cleaning course related data...')
            try:
                CourseEnrollment.objects.all().delete()
                TopicProgress.objects.all().delete()
                CourseTopic.objects.all().delete()
                Section.objects.all().delete()
                LearningObjective.objects.all().delete()
                CourseFeature.objects.all().delete()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cleaning course related data: {str(e)}'))

            # Clean Course and Topic data
            self.stdout.write('Cleaning course and topic data...')
            try:
                Topic.objects.all().delete()
                Course.objects.all().delete()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cleaning course and topic data: {str(e)}'))

        self.stdout.write(self.style.SUCCESS('Successfully cleaned all course-related data')) 