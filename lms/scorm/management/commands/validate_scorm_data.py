"""
Management command to validate SCORM data integrity.
This command checks for data consistency, validates relationships,
and identifies potential issues in SCORM tracking and package data.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging

from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course
from users.models import CustomUser

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Validate SCORM data integrity and consistency'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix identified issues',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Validate specific package by ID',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        verbose = options['verbose']
        package_id = options['package_id']
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        self.stdout.write(
            self.style.SUCCESS('Starting SCORM data validation...')
        )
        
        try:
            with transaction.atomic():
                issues_found = 0
                
                # 1. Validate SCORM packages
                issues_found += self.validate_packages(verbose, package_id, fix)
                
                # 2. Validate SCORM tracking records
                issues_found += self.validate_tracking_records(verbose, fix)
                
                # 3. Validate user relationships
                issues_found += self.validate_user_relationships(verbose, fix)
                
                # 4. Validate course relationships
                issues_found += self.validate_course_relationships(verbose, fix)
                
                # 5. Validate S3 file references
                issues_found += self.validate_s3_references(verbose, fix)
                
                if issues_found == 0:
                    self.stdout.write(
                        self.style.SUCCESS('No data integrity issues found!')
                    )
                else:
                    if fix:
                        self.stdout.write(
                            self.style.SUCCESS(f'Fixed {issues_found} data integrity issues')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'Found {issues_found} data integrity issues (use --fix to attempt repairs)')
                        )
                
        except Exception as e:
            logger.error(f"Error during SCORM validation: {str(e)}")
            raise CommandError(f'Validation failed: {str(e)}')

    def validate_packages(self, verbose=False, package_id=None, fix=False):
        """Validate SCORM package data integrity"""
        self.stdout.write('Validating SCORM packages...')
        
        issues = 0
        
        if package_id:
            packages = ELearningPackage.objects.filter(id=package_id)
        else:
            packages = ELearningPackage.objects.all()
        
        for package in packages:
            package_issues = []
            
            # Check for missing topic reference
            if not package.topic:
                package_issues.append("Missing topic reference")
                if fix:
                    # Try to find a topic with matching title
                    matching_topic = Topic.objects.filter(title__icontains=package.title).first()
                    if matching_topic:
                        package.topic = matching_topic
                        package.save()
                        self.stdout.write(f'Fixed package {package.id}: Assigned topic {matching_topic.id}')
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'Could not fix package {package.id}: No matching topic found')
                        )
            
            # Check for missing package file
            if not package.package_file:
                package_issues.append("Missing package file")
            
            # Check for missing extracted path
            if not package.extracted_path:
                package_issues.append("Missing extracted path")
            
            # Check for missing launch file
            if not package.launch_file:
                package_issues.append("Missing launch file")
            
            # Check for invalid package type
            if package.package_type not in [choice[0] for choice in ELearningPackage.PACKAGE_TYPES]:
                package_issues.append(f"Invalid package type: {package.package_type}")
                if fix:
                    package.package_type = 'SCORM_1_2'  # Default fallback
                    package.save()
                    self.stdout.write(f'Fixed package {package.id}: Set package type to SCORM_1_2')
            
            # Check for missing required fields
            if not package.title:
                package_issues.append("Missing title")
                if fix:
                    package.title = f"Package {package.id}"
                    package.save()
                    self.stdout.write(f'Fixed package {package.id}: Set default title')
            
            if package_issues:
                issues += len(package_issues)
                if verbose:
                    self.stdout.write(f'Package {package.id} issues: {", ".join(package_issues)}')
        
        return issues

    def validate_tracking_records(self, verbose=False, fix=False):
        """Validate SCORM tracking record data integrity"""
        self.stdout.write('Validating SCORM tracking records...')
        
        issues = 0
        
        for tracking in ELearningTracking.objects.all():
            tracking_issues = []
            
            # Check for missing user reference
            if not tracking.user:
                tracking_issues.append("Missing user reference")
                if fix:
                    tracking.delete()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Deleted orphaned record')
                    continue
            
            # Check for missing package reference
            if not tracking.elearning_package:
                tracking_issues.append("Missing package reference")
                if fix:
                    tracking.delete()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Deleted orphaned record')
                    continue
            
            # Check for invalid completion status
            valid_completion_statuses = ['incomplete', 'completed', 'unknown']
            if tracking.completion_status not in valid_completion_statuses:
                tracking_issues.append(f"Invalid completion status: {tracking.completion_status}")
                if fix:
                    tracking.completion_status = 'incomplete'
                    tracking.save()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Set completion status to incomplete')
            
            # Check for invalid success status
            valid_success_statuses = ['passed', 'failed', 'unknown']
            if tracking.success_status not in valid_success_statuses:
                tracking_issues.append(f"Invalid success status: {tracking.success_status}")
                if fix:
                    tracking.success_status = 'unknown'
                    tracking.save()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Set success status to unknown')
            
            # Check for invalid score values
            if tracking.score_raw is not None:
                if tracking.score_raw < 0 or tracking.score_raw > 100:
                    tracking_issues.append(f"Invalid score: {tracking.score_raw}")
                    if fix:
                        tracking.score_raw = max(0, min(100, tracking.score_raw))
                        tracking.save()
                        self.stdout.write(f'Fixed tracking {tracking.id}: Clamped score to valid range')
            
            # Check for invalid time values
            if tracking.total_time and tracking.total_time.total_seconds() < 0:
                tracking_issues.append("Invalid total time")
                if fix:
                    tracking.total_time = None
                    tracking.save()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Reset invalid total time')
            
            # Check for missing raw_data
            if not tracking.raw_data:
                tracking_issues.append("Missing raw data")
                if fix:
                    tracking.raw_data = {}
                    tracking.save()
                    self.stdout.write(f'Fixed tracking {tracking.id}: Initialized empty raw data')
            
            if tracking_issues:
                issues += len(tracking_issues)
                if verbose:
                    self.stdout.write(f'Tracking {tracking.id} issues: {", ".join(tracking_issues)}')
        
        return issues

    def validate_user_relationships(self, verbose=False, fix=False):
        """Validate user relationship integrity"""
        self.stdout.write('Validating user relationships...')
        
        issues = 0
        
        # Check for tracking records with invalid user references
        invalid_tracking = ELearningTracking.objects.filter(
            user__isnull=True
        )
        
        if invalid_tracking.exists():
            count = invalid_tracking.count()
            issues += count
            if verbose:
                self.stdout.write(f'Found {count} tracking records with invalid user references')
            
            if fix:
                invalid_tracking.delete()
                self.stdout.write(f'Fixed: Deleted {count} tracking records with invalid user references')
        
        # Check for tracking records with non-existent users
        for tracking in ELearningTracking.objects.exclude(user__isnull=True):
            try:
                # Try to access the user to see if it exists
                user = tracking.user
                if not user:
                    issues += 1
                    if verbose:
                        self.stdout.write(f'Tracking {tracking.id} has invalid user reference')
                    if fix:
                        tracking.delete()
                        self.stdout.write(f'Fixed: Deleted tracking {tracking.id} with invalid user')
            except Exception:
                issues += 1
                if verbose:
                    self.stdout.write(f'Tracking {tracking.id} has invalid user reference')
                if fix:
                    tracking.delete()
                    self.stdout.write(f'Fixed: Deleted tracking {tracking.id} with invalid user')
        
        return issues

    def validate_course_relationships(self, verbose=False, fix=False):
        """Validate course relationship integrity"""
        self.stdout.write('Validating course relationships...')
        
        issues = 0
        
        # Check for packages with invalid topic references
        invalid_packages = ELearningPackage.objects.filter(
            topic__isnull=True
        )
        
        if invalid_packages.exists():
            count = invalid_packages.count()
            issues += count
            if verbose:
                self.stdout.write(f'Found {count} packages with invalid topic references')
            
            if fix:
                # Try to find matching topics or delete packages
                for package in invalid_packages:
                    matching_topic = Topic.objects.filter(
                        title__icontains=package.title
                    ).first()
                    
                    if matching_topic:
                        package.topic = matching_topic
                        package.save()
                        self.stdout.write(f'Fixed: Assigned package {package.id} to topic {matching_topic.id}')
                    else:
                        package.delete()
                        self.stdout.write(f'Fixed: Deleted package {package.id} with no matching topic')
        
        # Check for tracking records with invalid package references
        invalid_tracking = ELearningTracking.objects.filter(
            elearning_package__isnull=True
        )
        
        if invalid_tracking.exists():
            count = invalid_tracking.count()
            issues += count
            if verbose:
                self.stdout.write(f'Found {count} tracking records with invalid package references')
            
            if fix:
                invalid_tracking.delete()
                self.stdout.write(f'Fixed: Deleted {count} tracking records with invalid package references')
        
        return issues

    def validate_s3_references(self, verbose=False, fix=False):
        """Validate S3 file reference integrity"""
        self.stdout.write('Validating S3 file references...')
        
        issues = 0
        
        try:
            from .storage import SCORMS3Storage
            storage = SCORMS3Storage()
            
            # Check for packages with missing S3 files
            for package in ELearningPackage.objects.exclude(package_file__isnull=True):
                if package.package_file:
                    try:
                        # Try to access the file
                        storage.open(package.package_file.name)
                    except Exception:
                        issues += 1
                        if verbose:
                            self.stdout.write(f'Package {package.id} has missing S3 file: {package.package_file.name}')
                        
                        if fix:
                            package.package_file = None
                            package.save()
                            self.stdout.write(f'Fixed: Cleared missing S3 file reference for package {package.id}')
            
            # Check for packages with missing extracted content
            for package in ELearningPackage.objects.exclude(extracted_path__isnull=True):
                if package.extracted_path:
                    try:
                        # Try to list the directory
                        storage.listdir(package.extracted_path)
                    except Exception:
                        issues += 1
                        if verbose:
                            self.stdout.write(f'Package {package.id} has missing extracted content: {package.extracted_path}')
                        
                        if fix:
                            package.extracted_path = None
                            package.is_extracted = False
                            package.save()
                            self.stdout.write(f'Fixed: Cleared missing extracted content reference for package {package.id}')
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error validating S3 references: {str(e)}')
            )
        
        return issues