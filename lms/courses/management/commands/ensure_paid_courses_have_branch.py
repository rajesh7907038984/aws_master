import logging
from django.core.management.base import BaseCommand
from courses.models import Course
from branches.models import Branch

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Ensures all paid courses have a branch assigned'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually updating the database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Get default branch if needed for assignment
        default_branch = Branch.objects.first()
        if not default_branch:
            self.stdout.write(self.style.ERROR('No branches found in the system. Cannot assign branches to courses.'))
            return
            
        # Find all paid courses without branches
        paid_courses_without_branch = Course.objects.filter(
            price__gt=0,
            branch__isnull=True
        )
        
        count = paid_courses_without_branch.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All paid courses already have branches assigned. No action needed.'))
            return
            
        self.stdout.write(f'Found {count} paid course(s) without branch assignment.')
        
        # Assign the default branch to each paid course
        for course in paid_courses_without_branch:
            self.stdout.write(f'Course: {course.title} (ID: {course.id}), Price: ${course.price}')
            if not dry_run:
                course.branch = default_branch
                course.save(update_fields=['branch'])
                self.stdout.write(self.style.SUCCESS(f'  - Assigned to branch: {default_branch.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'  - Would assign to branch: {default_branch.name} (dry run)'))
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'Successfully assigned branches to {count} paid courses.'))
        else:
            self.stdout.write(self.style.WARNING(f'Dry run complete. Would assign branches to {count} paid courses.')) 