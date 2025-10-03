"""

"""

from django.db import models
from django.conf import settings
import pytz

class IntegrationCredential(models.Model):
    """Base model for storing integration credentials"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, help_text="Name for this integration configuration")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
class PortalSettings(models.Model):
    """Model for storing portal settings"""
    branch = models.OneToOneField('branches.Branch', on_delete=models.CASCADE, related_name='portal_settings', 
                                null=True, blank=True, help_text="The branch these portal settings belong to")
    timezone = models.CharField(max_length=50, default='UTC', 
                              help_text="Default timezone for the portal")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Portal settings for {self.branch.name}"
    
    @property
    def timezone_choices(self):
        return [(tz, tz) for tz in pytz.common_timezones]
        
    class Meta:
        verbose_name = 'Portal Settings'
        verbose_name_plural = 'Portal Settings'

class TeamsIntegration(IntegrationCredential):
    """Model for storing Microsoft Teams API credentials"""
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    tenant_id = models.CharField(max_length=255)
    access_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(blank=True, null=True)
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True, help_text="The branch this integration belongs to")
    
    def __str__(self):
        return f"Teams - {self.name}"

class ZoomIntegration(IntegrationCredential):
    """Model for storing Zoom API credentials"""
    api_key = models.CharField(max_length=255)
    api_secret = models.CharField(max_length=255)
    oauth_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(blank=True, null=True)
    account_id = models.CharField(max_length=255, blank=True, null=True)
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True, help_text="The branch this integration belongs to")
    
    def __str__(self):
        return f"Zoom - {self.name}"

class StripeIntegration(IntegrationCredential):
    """Model for storing Stripe payment gateway credentials"""
    publishable_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    webhook_secret = models.CharField(max_length=255, blank=True, null=True)
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True, 
                              help_text="The branch this payment integration belongs to")
    is_test_mode = models.BooleanField(default=True, help_text="Whether to use test mode or live mode")
    
    def __str__(self):
        return f"Stripe - {self.name}"

class PayPalIntegration(IntegrationCredential):
    """Model for storing PayPal payment gateway credentials"""
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True,
                              help_text="The branch this payment integration belongs to")
    is_sandbox = models.BooleanField(default=True, help_text="Whether to use sandbox or live mode")
    
    def __str__(self):
        return f"PayPal - {self.name}"
class SharePointIntegration(IntegrationCredential):
    """Model for storing SharePoint API credentials"""
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    tenant_id = models.CharField(max_length=255)
    site_url = models.URLField(help_text="SharePoint site URL")
    access_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(blank=True, null=True)
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True, 
                              help_text="The branch this integration belongs to")
    
    def __str__(self):
        return f"SharePoint - {self.name}"

class ExportJob(models.Model):
    """Model for tracking data export jobs"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    job_type = models.CharField(max_length=50, choices=[
        ('full_export', 'Full Data Export'),
        ('user_export', 'User Data Export'),
        ('course_export', 'Course Data Export'),
        ('activity_export', 'Activity Data Export'),
    ])
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    file_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Export {self.job_type} - {self.status}"

class ImportJob(models.Model):
    """Model for tracking data import jobs"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    job_type = models.CharField(max_length=50, choices=[
        ('user_import', 'User Data Import'),
        ('course_import', 'Course Data Import'),
        ('bulk_enrollment', 'Bulk Enrollment'),
    ])
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    file_path = models.CharField(max_length=500)
    results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Import {self.job_type} - {self.status}"

class DataBackup(models.Model):
    """Model for tracking database backups"""
    backup_type = models.CharField(max_length=20, choices=[
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
        ('pre_update', 'Pre-Update'),
    ])
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    file_path = models.CharField(max_length=500, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True, help_text="Backup file size in bytes")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"Backup {self.backup_type} - {self.status}"

class GlobalAdminSettings(models.Model):
    """Model for storing global admin settings"""
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.TextField()
    description = models.TextField(blank=True, null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.setting_key}: {self.setting_value[:50]}"
    
    class Meta:
        verbose_name = 'Global Admin Setting'
        verbose_name_plural = 'Global Admin Settings'

class MenuControlSettings(models.Model):
    """Model for storing branch-specific menu control settings"""
    branch = models.OneToOneField('branches.Branch', on_delete=models.CASCADE, related_name='menu_settings')
    
    # Dashboard Menu Controls
    show_dashboard_overview = models.BooleanField(default=True)
    show_dashboard_analytics = models.BooleanField(default=True)
    show_dashboard_quick_actions = models.BooleanField(default=True)
    
    # Course Menu Controls
    show_course_creation = models.BooleanField(default=True)
    show_course_management = models.BooleanField(default=True)
    show_course_categories = models.BooleanField(default=True)
    
    # User Menu Controls
    show_user_management = models.BooleanField(default=True)
    show_user_roles = models.BooleanField(default=True)
    show_user_groups = models.BooleanField(default=True)
    
    # Reports Menu Controls
    show_progress_reports = models.BooleanField(default=True)
    show_completion_reports = models.BooleanField(default=True)
    show_activity_reports = models.BooleanField(default=True)
    
    # Tools Menu Controls
    show_integrations = models.BooleanField(default=True)
    show_data_management = models.BooleanField(default=True)
    show_system_settings = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"Menu settings for {self.branch.name}"
    
    class Meta:
        verbose_name = 'Menu Control Setting'
        verbose_name_plural = 'Menu Control Settings'
