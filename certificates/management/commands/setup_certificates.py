"""
Management command to setup certificate generation for courses
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from courses.models import Course, CourseEnrollment
from certificates.models import CertificateTemplate, IssuedCertificate
from users.models import CustomUser
import uuid
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Setup certificate generation for courses and generate missing certificates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable-all',
            action='store_true',
            help='Enable certificate generation for all courses',
        )
        parser.add_argument(
            '--course-id',
            type=int,
            help='Enable certificate generation for a specific course ID',
        )
        parser.add_argument(
            '--template-id',
            type=int,
            help='Use a specific certificate template ID',
        )
        parser.add_argument(
            '--generate-missing',
            action='store_true',
            help='Generate missing certificates for completed courses',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Certificate Setup Command ==='))
        
        # Get certificate template
        template = None
        if options['template_id']:
            try:
                template = CertificateTemplate.objects.get(id=options['template_id'])
                self.stdout.write(f"Using template: {template.name}")
            except CertificateTemplate.DoesNotExist:
                raise CommandError(f"Certificate template with ID {options['template_id']} not found")
        else:
            # Use the first active template
            template = CertificateTemplate.objects.filter(is_active=True).first()
            if not template:
                raise CommandError("No active certificate templates found. Please create one first.")
            self.stdout.write(f"Using default template: {template.name}")
        
        # Enable certificate generation for courses
        if options['enable_all']:
            self.enable_certificates_for_all_courses(template, options['dry_run'])
        elif options['course_id']:
            self.enable_certificates_for_course(options['course_id'], template, options['dry_run'])
        else:
            self.stdout.write("No action specified. Use --enable-all or --course-id")
            return
        
        # Generate missing certificates
        if options['generate_missing']:
            self.generate_missing_certificates(template, options['dry_run'])

    def enable_certificates_for_all_courses(self, template, dry_run):
        """Enable certificate generation for all courses"""
        courses = Course.objects.all()
        self.stdout.write(f"Found {courses.count()} courses")
        
        updated_count = 0
        for course in courses:
            if not course.issue_certificate or not course.certificate_template:
                if not dry_run:
                    course.issue_certificate = True
                    course.certificate_template = template
                    course.save()
                self.stdout.write(f"  - Enabled certificates for: {course.title}")
                updated_count += 1
        
        if dry_run:
            self.stdout.write(f"DRY RUN: Would enable certificates for {updated_count} courses")
        else:
            self.stdout.write(f"Enabled certificates for {updated_count} courses")

    def enable_certificates_for_course(self, course_id, template, dry_run):
        """Enable certificate generation for a specific course"""
        try:
            course = Course.objects.get(id=course_id)
            if not dry_run:
                course.issue_certificate = True
                course.certificate_template = template
                course.save()
            self.stdout.write(f"Enabled certificates for course: {course.title}")
        except Course.DoesNotExist:
            raise CommandError(f"Course with ID {course_id} not found")

    def generate_missing_certificates(self, template, dry_run):
        """Generate missing certificates for completed courses"""
        # Find courses with certificate generation enabled
        courses_with_certificates = Course.objects.filter(
            issue_certificate=True,
            certificate_template__isnull=False
        )
        
        self.stdout.write(f"Found {courses_with_certificates.count()} courses with certificate generation enabled")
        
        generated_count = 0
        for course in courses_with_certificates:
            # Find completed enrollments without certificates
            completed_enrollments = CourseEnrollment.objects.filter(
                course=course,
                completed=True
            )
            
            for enrollment in completed_enrollments:
                # Check if certificate already exists
                existing_cert = IssuedCertificate.objects.filter(
                    recipient=enrollment.user,
                    course_name=course.title
                ).first()
                
                if not existing_cert:
                    if not dry_run:
                        # Generate unique certificate number
                        certificate_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
                        
                        # Get course instructor or superuser as issuer
                        issuer = course.instructor
                        if not issuer:
                            issuer = CustomUser.objects.filter(is_superuser=True).first()
                        
                        if not issuer:
                            issuer = enrollment.user  # Fallback
                        
                        # Create certificate
                        certificate = IssuedCertificate.objects.create(
                            template=course.certificate_template,
                            recipient=enrollment.user,
                            issued_by=issuer,
                            course_name=course.title,
                            certificate_number=certificate_number,
                        )
                        
                        self.stdout.write(f"  - Generated certificate {certificate.certificate_number} for {enrollment.user.username} in {course.title}")
                    else:
                        self.stdout.write(f"  - Would generate certificate for {enrollment.user.username} in {course.title}")
                    
                    generated_count += 1
        
        if dry_run:
            self.stdout.write(f"DRY RUN: Would generate {generated_count} certificates")
        else:
            self.stdout.write(f"Generated {generated_count} certificates")
