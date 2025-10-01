"""
Course completion signals for certificate generation
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import logging
import uuid

from courses.models import CourseEnrollment
from certificates.models import IssuedCertificate

logger = logging.getLogger(__name__)

@receiver(post_save, sender=CourseEnrollment)
def handle_course_completion(sender, instance, created, **kwargs):
    """
    Handle course completion and generate certificates
    This signal ensures certificates are generated when courses are completed
    """
    # Only process if this is an update (not creation) and completion status changed
    if created:
        return
    
    # Check if completion status changed from False to True
    if not instance.completed:
        return
    
    # Check if completion date was just set (indicating recent completion)
    if not instance.completion_date:
        return
    
    # Only process if completion happened recently (within last hour)
    time_diff = timezone.now() - instance.completion_date
    if time_diff.total_seconds() > 3600:  # More than 1 hour ago
        return
    
    try:
        course = instance.course
        user = instance.user
        
        logger.info(f"Processing course completion for {user.username} in course '{course.title}'")
        
        # Check if certificate generation is enabled for this course
        if not (course.issue_certificate and course.certificate_template):
            logger.info(f"Certificate generation not enabled for course '{course.title}' (issue_certificate={course.issue_certificate}, template={course.certificate_template})")
            return
        
        # Check if certificate already exists
        existing_cert = IssuedCertificate.objects.filter(
            recipient=user,
            course_name=course.title
        ).first()
        
        if existing_cert:
            logger.info(f"Certificate already exists for {user.username} in course '{course.title}': {existing_cert.certificate_number}")
            return
        
        # Generate unique certificate number
        certificate_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
        
        # Get course instructor or superuser as issuer
        issuer = course.instructor
        if not issuer:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            issuer = User.objects.filter(is_superuser=True).first()
        
        if not issuer:
            logger.warning(f"No issuer found for certificate generation for course '{course.title}'")
            issuer = user  # Fallback to user themselves
        
        # Create certificate
        certificate = IssuedCertificate.objects.create(
            template=course.certificate_template,
            recipient=user,
            issued_by=issuer,
            course_name=course.title,
            certificate_number=certificate_number,
        )
        
        logger.info(f"Auto-generated certificate {certificate.certificate_number} for {user.username} for course '{course.title}'")
        
    except Exception as e:
        logger.error(f"Error generating certificate for {instance.user.username} in course '{instance.course.title}': {str(e)}")
