from django.core.management.base import BaseCommand
from assignments.models import Assignment
from assignments.views import sync_assignment_courses
from django.db import transaction

class Command(BaseCommand):
    help = 'Synchronize course relationships for all assignments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--id',
            type=int,
            help='Sync a specific assignment by ID',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of assignments to process in each batch',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting assignment-course synchronization...'))
        
        batch_size = options['batch_size']
        specific_id = options.get('id')
        
        if specific_id:
            try:
                assignment = Assignment.objects.get(id=specific_id)
                self.sync_single_assignment(assignment)
                self.stdout.write(self.style.SUCCESS(f'Successfully synchronized assignment {specific_id}'))
            except Assignment.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Assignment with ID {specific_id} not found'))
                return
        else:
            # Get total count for progress reporting
            total_count = Assignment.objects.count()
            self.stdout.write(self.style.SUCCESS(f'Found {total_count} assignments to process'))
            
            # Process in batches to avoid memory issues
            processed = 0
            
            # Get all assignments in batches
            while True:
                assignments = Assignment.objects.all().order_by('id')[processed:processed+batch_size]
                if not assignments:
                    break
                
                self.process_batch(assignments)
                processed += len(assignments)
                self.stdout.write(self.style.SUCCESS(f'Processed {processed}/{total_count} assignments'))
        
        self.stdout.write(self.style.SUCCESS('Assignment-course synchronization completed successfully!'))
    
    def process_batch(self, assignments):
        """Process a batch of assignments"""
        with transaction.atomic():
            for assignment in assignments:
                self.sync_single_assignment(assignment)
    
    def sync_single_assignment(self, assignment):
        """Sync a single assignment's course relationships"""
        # Store counts before sync for reporting
        before_count = assignment.courses.count()
        
        # Perform the sync
        sync_assignment_courses(assignment)
        
        # Get counts after sync for reporting
        after_count = assignment.courses.count()
        
        # Report changes
        if before_count != after_count:
            self.stdout.write(f'Assignment ID {assignment.id}: Courses changed from {before_count} to {after_count}')
            
            # List the courses
            courses = assignment.courses.all()
            primary_course = assignment.course
            
            course_list = []
            for course in courses:
                is_primary = primary_course and primary_course.id == course.id
                course_list.append(f"{course.id}: {course.title}" + (" (Primary)" if is_primary else ""))
            
            self.stdout.write(f'  Courses: {", ".join(course_list)}')
        else:
            self.stdout.write(f'Assignment ID {assignment.id}: No changes needed ({before_count} courses)') 