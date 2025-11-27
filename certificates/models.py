from django.db import models
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class CertificateTemplate(models.Model):
    """Model for storing certificate templates"""
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='certificate_templates/%Y/%m/%d/')
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
    
    def save(self, *args, **kwargs):
        """Override save to track storage usage"""
        is_new = self.pk is None
        old_image = None
        
        if not is_new and self.image:
            try:
                old_instance = CertificateTemplate.objects.get(pk=self.pk)
                old_image = old_instance.image
            except CertificateTemplate.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Register certificate template upload with storage tracking
        if self.image and (is_new or (old_image != self.image)):
            try:
                from core.utils.storage_manager import StorageManager
                from django.core.files.storage import default_storage
                
                # Get file size
                file_size = self.image.size if hasattr(self.image, 'size') else 0
                
                # If file_size is 0, try to get it from storage
                if file_size == 0:
                    try:
                        file_size = default_storage.size(self.image.name)
                    except Exception:
                        file_size = 0
                
                if file_size > 0 and self.created_by and self.created_by.branch:
                    StorageManager.register_file_upload(
                        user=self.created_by,
                        file_path=self.image.name,
                        original_filename=self.name,
                        file_size_bytes=file_size,
                        content_type='image/jpeg',
                        source_app='certificates',
                        source_model='CertificateTemplate',
                        source_object_id=self.id
                    )
                    logger.info(f"Registered certificate template upload: {self.name} - {file_size} bytes")
            except Exception as e:
                logger.error(f"Error registering certificate template upload: {str(e)}")
    
    def get_image_url(self):
        """
        Get the certificate background image URL without any modifications.
        Returns the original uploaded image URL exactly as-is.
        """
        if self.image:
            try:
                return self.image.url
            except Exception:
                # If URL generation fails, construct it manually
                media_url = getattr(settings, 'MEDIA_URL', '/media/')
                return f"{media_url.rstrip('/')}/{self.image.name}"
        return None
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up template image when deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Delete the template image if it exists
            if self.image:
                try:
                    self.image.delete(save=False)
                    logger.info(f"Deleted certificate template image for template: {self.name}")
                except Exception as e:
                    logger.error(f"Error deleting certificate template image: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in CertificateTemplate.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)

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
    certificate_file = models.FileField(upload_to='issued_certificates/%Y/%m/%d/', null=True, blank=True)
    certificate_number = models.CharField(max_length=100, unique=True)
    is_revoked = models.BooleanField(default=False)
    revocation_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate #{self.certificate_number} for {self.recipient.username}"
    
    def save(self, *args, **kwargs):
        """Override save to track storage usage"""
        is_new = self.pk is None
        old_certificate_file = None
        
        if not is_new and self.certificate_file:
            try:
                old_instance = IssuedCertificate.objects.get(pk=self.pk)
                old_certificate_file = old_instance.certificate_file
            except IssuedCertificate.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Register issued certificate upload with storage tracking
        if self.certificate_file and (is_new or (old_certificate_file != self.certificate_file)):
            try:
                from core.utils.storage_manager import StorageManager
                from django.core.files.storage import default_storage
                
                # Get file size
                file_size = self.certificate_file.size if hasattr(self.certificate_file, 'size') else 0
                
                # If file_size is 0, try to get it from storage
                if file_size == 0:
                    try:
                        file_size = default_storage.size(self.certificate_file.name)
                    except Exception:
                        file_size = 0
                
                if file_size > 0 and self.recipient and self.recipient.branch:
                    StorageManager.register_file_upload(
                        user=self.recipient,
                        file_path=self.certificate_file.name,
                        original_filename=f"Certificate_{self.certificate_number}.pdf",
                        file_size_bytes=file_size,
                        content_type='application/pdf',
                        source_app='certificates',
                        source_model='IssuedCertificate',
                        source_object_id=self.id
                    )
                    logger.info(f"Registered issued certificate upload: {self.certificate_number} - {file_size} bytes")
            except Exception as e:
                logger.error(f"Error registering issued certificate upload: {str(e)}")
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up certificate PDF file when deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Delete the certificate file if it exists
            if self.certificate_file:
                try:
                    self.certificate_file.delete(save=False)
                    logger.info(f"Deleted certificate file for certificate #{self.certificate_number}")
                except Exception as e:
                    logger.error(f"Error deleting certificate file: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in IssuedCertificate.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)
