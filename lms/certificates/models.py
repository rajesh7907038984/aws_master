from django.db import models
from django.conf import settings
from django.utils import timezone
from core.s3_storage import MediaS3Storage

class CertificateTemplate(models.Model):
    """Model for storing certificate templates"""
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='certificate_templates/%Y/%m/%d/', storage=MediaS3Storage())
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_templates'
    )
    validity_days = models.IntegerField(
        default=0,
        help_text="Number of days the certificate is valid (0 = no expiry)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """Enhanced delete method with S3 cleanup for certificate files."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting deletion for CertificateTemplate: {self.name} (ID: {self.id})")
            
            # Delete certificate template image
            if self.image:
                try:
                    self.image.delete(save=False)
                    logger.info(f"Deleted certificate template image: {self.image.name}")
                except Exception as e:
                    logger.error(f"Error deleting certificate template image: {e}")
            
            # S3 cleanup
            try:
                from core.utils.s3_cleanup import cleanup_certificate_s3_files
                s3_results = cleanup_certificate_s3_files(self.id)
                successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                total_s3_files = len(s3_results)
                if total_s3_files > 0:
                    logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} certificate files deleted successfully")
            except Exception as e:
                logger.error(f"Error during S3 cleanup for certificate template {self.id}: {str(e)}")
            
            # Call parent delete to remove the database record
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed deletion for CertificateTemplate: {self.name} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in CertificateTemplate.delete(): {str(e)}")
            raise

class CertificateElement(models.Model):
    """Model for storing certificate design elements"""
    ELEMENT_TYPES = (
        ('text', 'Text'),
        ('name', 'Name'),
        ('grade', 'Grade'),
        ('date', 'Date'),
        ('expiry_date', 'Expiry Date'),
        ('signature', 'Signature'),
        ('image', 'Image'),
        ('course', 'Course Name'),
    )

    template = models.ForeignKey(CertificateTemplate, on_delete=models.CASCADE, related_name='elements')
    element_type = models.CharField(max_length=50, choices=ELEMENT_TYPES)
    label = models.CharField(max_length=255)
    default_value = models.CharField(max_length=255, null=True, blank=True)
    position_x = models.FloatField(help_text="X coordinate in percentage (0-100)")
    position_y = models.FloatField(help_text="Y coordinate in percentage (0-100)")
    width = models.FloatField(default=20.0, help_text="Width in percentage (0-100)")
    height = models.FloatField(default=10.0, help_text="Height in percentage (0-100)")
    font_size = models.IntegerField(default=14, null=True, blank=True)
    font_family = models.CharField(max_length=100, null=True, blank=True, default="Arial, sans-serif")
    font_weight = models.CharField(max_length=50, null=True, blank=True, default="normal")
    color = models.CharField(max_length=50, null=True, blank=True, default="#000000")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.label} ({self.element_type}) on {self.template.name}"

class IssuedCertificate(models.Model):
    """Model for storing issued certificates"""
    template = models.ForeignKey(CertificateTemplate, on_delete=models.CASCADE, related_name='issued_certificates')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='certificates')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='issued_certificates')
    course_name = models.CharField(max_length=255, null=True, blank=True)
    grade = models.CharField(max_length=50, null=True, blank=True)
    issue_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(null=True, blank=True)
    certificate_file = models.FileField(upload_to='issued_certificates/%Y/%m/%d/', storage=MediaS3Storage(), null=True, blank=True)
    certificate_number = models.CharField(max_length=100, unique=True)
    is_revoked = models.BooleanField(default=False)
    revocation_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate #{self.certificate_number} for {self.recipient.username}"

    def delete(self, *args, **kwargs):
        """Enhanced delete method with S3 cleanup for issued certificate files."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting deletion for IssuedCertificate: {self.certificate_number} (ID: {self.id})")
            
            # Delete certificate file
            if self.certificate_file:
                try:
                    self.certificate_file.delete(save=False)
                    logger.info(f"Deleted issued certificate file: {self.certificate_file.name}")
                except Exception as e:
                    logger.error(f"Error deleting issued certificate file: {e}")
            
            # S3 cleanup
            try:
                from core.utils.s3_cleanup import cleanup_issued_certificate_s3_files
                s3_results = cleanup_issued_certificate_s3_files(self.id)
                successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                total_s3_files = len(s3_results)
                if total_s3_files > 0:
                    logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} issued certificate files deleted successfully")
            except Exception as e:
                logger.error(f"Error during S3 cleanup for issued certificate {self.id}: {str(e)}")
            
            # Call parent delete to remove the database record
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed deletion for IssuedCertificate: {self.certificate_number} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in IssuedCertificate.delete(): {str(e)}")
            raise
