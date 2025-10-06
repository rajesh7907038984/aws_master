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

class SCORMIntegration(IntegrationCredential):
    """Model for storing branch-specific SCORM Cloud API credentials"""
    app_id = models.CharField(max_length=255, help_text="SCORM Cloud Application ID")
    secret_key = models.CharField(max_length=255, help_text="SCORM Cloud Secret Key")
    pens_key = models.CharField(max_length=255, blank=True, null=True, help_text="SCORM Cloud PENS (Package Exchange Notification Services) Key for notifications")
    base_url = models.URLField(
        default='https://cloud.scorm.com/api/v2', 
        help_text="SCORM Cloud API Base URL"
    )
    verify_ssl = models.BooleanField(default=True, help_text="Verify SSL certificates for SCORM Cloud API")
    request_timeout = models.PositiveIntegerField(
        default=900, 
        help_text="Request timeout in seconds (15 minutes default)"
    )
    upload_timeout = models.PositiveIntegerField(
        default=1800, 
        help_text="Upload timeout in seconds (30 minutes default)"
    )
    max_upload_size = models.PositiveIntegerField(
        default=629145600, 
        help_text="Maximum upload size in bytes (600MB default)"
    )
    branch = models.ForeignKey(
        'branches.Branch', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="The branch this SCORM integration belongs to"
    )
    
    # Test status tracking
    is_tested = models.BooleanField(default=False, help_text="Whether SCORM Cloud configuration has been tested successfully")
    last_test_date = models.DateTimeField(null=True, blank=True, help_text="Date when SCORM Cloud configuration was last tested")
    test_error = models.TextField(blank=True, null=True, help_text="Last SCORM Cloud test error message if any")
    
    def __str__(self):
        return f"SCORM - {self.name}"
    
    def test_connection(self):
        """Test the SCORM Cloud configuration"""
        if not self.app_id or not self.secret_key:
            return False, "SCORM Cloud credentials are missing"
        
        try:
            # Import the SCORM Cloud API class
            from scorm_cloud.utils.api import SCORMCloudAPI
            from django.utils import timezone
            import requests
            
            # Create API instance with configured credentials
            api = SCORMCloudAPI(
                app_id=self.app_id,
                secret_key=self.secret_key
            )
            
            # Override the base URL and other settings for branch-specific configuration
            api.base_url = self.base_url
            api.verify_ssl = self.verify_ssl
            api.request_timeout = self.request_timeout
            
            # Check if API is properly configured first
            if not api.is_configured:
                error_msg = "SCORM Cloud API initialization failed - check your credentials"
                self.is_tested = False
                self.test_error = error_msg
                self.save(update_fields=['is_tested', 'test_error'])
                return False, error_msg
            
            # Test the connection by making a direct HTTP request
            try:
                headers = api._get_headers('application/json')
                test_url = f"{api.base_url}/ping"
                
                response = requests.get(
                    test_url,
                    headers=headers,
                    verify=self.verify_ssl,
                    timeout=10
                )
                
                if response.status_code == 200:
                    # Connection successful
                    self.is_tested = True
                    self.last_test_date = timezone.now()
                    self.test_error = ""
                    self.save(update_fields=['is_tested', 'last_test_date', 'test_error'])
                    return True, "SCORM Cloud connection successful"
                else:
                    error_msg = f"SCORM Cloud API returned status {response.status_code}"
                    if response.status_code == 401:
                        error_msg += " - Invalid credentials"
                    elif response.status_code == 403:
                        error_msg += " - Access forbidden"
                    elif response.status_code == 404:
                        error_msg += " - Endpoint not found"
                    
                    self.is_tested = False
                    self.test_error = error_msg
                    self.save(update_fields=['is_tested', 'test_error'])
                    return False, error_msg
                    
            except Exception as api_error:
                error_str = str(api_error)
                self.is_tested = False
                self.test_error = error_str
                self.save(update_fields=['is_tested', 'test_error'])
                return False, error_str
                
        except ImportError:
            error_msg = "SCORM Cloud API module not available"
            self.is_tested = False
            self.test_error = error_msg
            self.save(update_fields=['is_tested', 'test_error'])
            return False, error_msg
        except Exception as e:
            error_msg = f"Failed to test SCORM Cloud connection: {str(e)}"
            self.is_tested = False
            self.test_error = error_msg
            self.save(update_fields=['is_tested', 'test_error'])
            return False, error_msg


class SharePointIntegration(IntegrationCredential):
    """Model for storing SharePoint integration credentials and configuration"""
    
    # SharePoint Authentication
    tenant_id = models.CharField(max_length=255, help_text="Microsoft Azure AD Tenant ID")
    client_id = models.CharField(max_length=255, help_text="Azure App Registration Application (client) ID")
    client_secret = models.CharField(max_length=255, help_text="Azure App Registration Client Secret")
    site_url = models.URLField(help_text="SharePoint site URL (e.g., https://company.sharepoint.com/sites/sitename)")
    
    # SharePoint Lists/Libraries Configuration
    user_list_name = models.CharField(max_length=255, default="LMS Users", help_text="SharePoint list name for user data")
    enrollment_list_name = models.CharField(max_length=255, default="Course Enrollments", help_text="SharePoint list name for course enrollments")
    progress_list_name = models.CharField(max_length=255, default="Learning Progress", help_text="SharePoint list name for progress tracking")
    certificate_library_name = models.CharField(max_length=255, default="Certificates", help_text="SharePoint document library name for certificates")
    reports_library_name = models.CharField(max_length=255, default="Reports", help_text="SharePoint document library name for reports")
    assessment_library_name = models.CharField(max_length=255, default="Assessments", help_text="SharePoint document library name for assessment results")
    
    # Power BI Integration
    powerbi_workspace_id = models.CharField(max_length=255, blank=True, null=True, help_text="Power BI workspace ID for analytics integration")
    powerbi_dataset_id = models.CharField(max_length=255, blank=True, null=True, help_text="Power BI dataset ID for LMS analytics")
    
    # Sync Configuration
    enable_user_sync = models.BooleanField(default=True, help_text="Enable user data synchronization")
    enable_enrollment_sync = models.BooleanField(default=True, help_text="Enable enrollment synchronization")
    enable_progress_sync = models.BooleanField(default=True, help_text="Enable progress synchronization")
    enable_certificate_sync = models.BooleanField(default=True, help_text="Enable certificate synchronization")
    enable_reports_sync = models.BooleanField(default=True, help_text="Enable reports synchronization")
    enable_assessment_sync = models.BooleanField(default=True, help_text="Enable assessment synchronization")
    
    # Authentication Token Storage
    access_token = models.TextField(blank=True, null=True, help_text="Current access token for SharePoint API")
    token_expiry = models.DateTimeField(blank=True, null=True, help_text="Access token expiry time")
    refresh_token = models.TextField(blank=True, null=True, help_text="Refresh token for token renewal")
    
    # Sync Status and Monitoring
    last_sync_datetime = models.DateTimeField(blank=True, null=True, help_text="Last successful synchronization datetime")
    last_sync_status = models.CharField(max_length=50, default='never', help_text="Status of last sync attempt")
    sync_error_message = models.TextField(blank=True, null=True, help_text="Error message from last sync attempt")
    total_synced_users = models.PositiveIntegerField(default=0, help_text="Total users synchronized")
    total_synced_enrollments = models.PositiveIntegerField(default=0, help_text="Total enrollments synchronized")
    
    # Branch Association
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, null=True, blank=True,
                              help_text="The branch this SharePoint integration belongs to")
    
    class Meta:
        verbose_name = 'SharePoint Integration'
        verbose_name_plural = 'SharePoint Integrations'
    
    def __str__(self):
        return f"SharePoint - {self.name}"
    
    def is_token_valid(self):
        """Check if the access token is still valid"""
        if not self.access_token or not self.token_expiry:
            return False
        from django.utils import timezone
        return timezone.now() < self.token_expiry
    
    def needs_token_refresh(self):
        """Check if token needs refresh (expires within 5 minutes)"""
        if not self.token_expiry:
            return True
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() + timedelta(minutes=5) >= self.token_expiry
    
    def get_site_domain(self):
        """Extract domain from SharePoint site URL"""
        from urllib.parse import urlparse
        parsed = urlparse(self.site_url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def get_site_path(self):
        """Extract site path from SharePoint site URL"""
        from urllib.parse import urlparse
        parsed = urlparse(self.site_url)
        return parsed.path.rstrip('/')

class ExportJob(models.Model):
    """Model for tracking data export jobs"""
    EXPORT_TYPE_CHOICES = [
        ('users', 'Users'),
        ('courses', 'Courses'),
        ('topics', 'Topics'),
        ('assignments', 'Assignments'),
        ('quizzes', 'Quizzes'),
        ('discussions', 'Discussions'),
        ('conferences', 'Conferences'),
        ('all', 'All Data'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='export_jobs', null=True, blank=True)
    export_type = models.CharField(max_length=20, choices=EXPORT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_path = models.CharField(max_length=500, null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    record_count = models.IntegerField(null=True, blank=True, help_text="Number of records exported")
    error_message = models.TextField(null=True, blank=True)
    include_files = models.BooleanField(default=True, help_text="Include related files in export")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.export_type.title()} Export - {self.status}"

class ImportJob(models.Model):
    """Model for tracking data import jobs"""
    IMPORT_TYPE_CHOICES = [
        ('users', 'Users'),
        ('courses', 'Courses'),
        ('topics', 'Topics'),
        ('assignments', 'Assignments'),
        ('quizzes', 'Quizzes'),
        ('discussions', 'Discussions'),
        ('conferences', 'Conferences'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='import_jobs', null=True, blank=True)
    import_type = models.CharField(max_length=20, choices=IMPORT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_path = models.CharField(max_length=500)
    records_processed = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)
    validation_errors = models.JSONField(default=dict, help_text="Detailed validation errors")
    replace_existing = models.BooleanField(default=False, help_text="Replace existing records")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.import_type.title()} Import - {self.status}"

class DataBackup(models.Model):
    """Model for storing automatic system backups"""
    BACKUP_TYPE_CHOICES = [
        ('manual', 'Manual Backup'),
        ('scheduled', 'Scheduled Backup'),
        ('pre_import', 'Pre-Import Backup'),
    ]
    
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPE_CHOICES)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(help_text="File size in bytes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.backup_type.title()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class GlobalAdminSettings(models.Model):
    """Global Admin settings for system-wide configuration"""
    # Google OAuth Configuration
    google_oauth_enabled = models.BooleanField(default=True, help_text="Enable Google OAuth for the entire system")
    google_client_id = models.CharField(max_length=255, blank=True, null=True, help_text="Google OAuth Client ID")
    google_client_secret = models.CharField(max_length=255, blank=True, null=True, help_text="Google OAuth Client Secret")
    google_oauth_domains = models.TextField(blank=True, null=True, help_text="Allowed domains for Google OAuth (comma separated)")
    
    # Microsoft OAuth Configuration
    microsoft_oauth_enabled = models.BooleanField(default=True, help_text="Enable Microsoft OAuth for the entire system")
    microsoft_client_id = models.CharField(max_length=255, blank=True, null=True, help_text="Microsoft OAuth Client ID (Application ID)")
    microsoft_client_secret = models.CharField(max_length=255, blank=True, null=True, help_text="Microsoft OAuth Client Secret")
    microsoft_tenant_id = models.CharField(max_length=255, blank=True, null=True, help_text="Microsoft Tenant ID (optional, use 'common' for multi-tenant)")
    microsoft_oauth_domains = models.TextField(blank=True, null=True, help_text="Allowed domains for Microsoft OAuth (comma separated)")
    

    
    # Master SMTP Configuration
    smtp_enabled = models.BooleanField(default=False, help_text="Enable custom SMTP configuration for all email sending")
    smtp_host = models.CharField(max_length=255, blank=True, null=True, help_text="SMTP server hostname (e.g., smtp.gmail.com)")
    smtp_port = models.PositiveIntegerField(default=587, help_text="SMTP server port (usually 587 for TLS, 465 for SSL, 25 for plain)")
    smtp_username = models.CharField(max_length=255, blank=True, null=True, help_text="SMTP username/email address")
    smtp_password = models.CharField(max_length=255, blank=True, null=True, help_text="SMTP password")
    smtp_use_tls = models.BooleanField(default=True, help_text="Use TLS encryption (recommended)")
    smtp_use_ssl = models.BooleanField(default=False, help_text="Use SSL encryption (alternative to TLS)")
    smtp_from_email = models.EmailField(blank=True, null=True, help_text="Default 'From' email address for all notifications")
    smtp_from_name = models.CharField(max_length=255, default="LMS Notifications", help_text="Display name for the 'From' field")
    smtp_reply_to_email = models.EmailField(blank=True, null=True, help_text="Reply-to email address (optional)")
    smtp_is_tested = models.BooleanField(default=False, help_text="Whether SMTP configuration has been tested successfully")
    smtp_last_test_date = models.DateTimeField(null=True, blank=True, help_text="Date when SMTP configuration was last tested")
    smtp_test_error = models.TextField(blank=True, null=True, help_text="Last SMTP test error message if any")
    
    # SharePoint Integration Global Settings
    sharepoint_integration_enabled = models.BooleanField(default=False, help_text="Enable SharePoint integration system-wide")
    sharepoint_sync_users = models.BooleanField(default=True, help_text="Enable user data synchronization with SharePoint")
    sharepoint_sync_enrollments = models.BooleanField(default=True, help_text="Enable course enrollment synchronization with SharePoint")
    sharepoint_sync_progress = models.BooleanField(default=True, help_text="Enable progress tracking synchronization to SharePoint")
    sharepoint_sync_certificates = models.BooleanField(default=True, help_text="Enable completion certificates sync to SharePoint libraries")
    sharepoint_sync_reports = models.BooleanField(default=True, help_text="Enable LMS analytics sync to Power BI via SharePoint")
    sharepoint_sync_assessments = models.BooleanField(default=True, help_text="Enable assessment results sync to SharePoint & documents")
    sharepoint_sync_interval = models.PositiveIntegerField(default=60, help_text="Sync interval in minutes for automatic synchronization")
    sharepoint_auto_sync_enabled = models.BooleanField(default=False, help_text="Enable automatic scheduled synchronization")
    
    # Order Management Global Settings
    order_management_enabled = models.BooleanField(default=False, help_text="Enable order management features system-wide")
    
    # Anthropic AI Configuration
    anthropic_ai_enabled = models.BooleanField(default=False, help_text="Enable Anthropic AI content generation for TinyMCE editors system-wide")
    anthropic_api_key = models.CharField(max_length=255, blank=True, null=True, help_text="Anthropic API Key for Claude AI content generation")
    anthropic_model = models.CharField(max_length=100, default='claude-3-5-sonnet-20241022', help_text="Anthropic model to use for content generation")
    anthropic_max_tokens = models.PositiveIntegerField(default=1000, help_text="Maximum tokens per AI request")
    anthropic_is_tested = models.BooleanField(default=False, help_text="Whether Anthropic AI configuration has been tested successfully")
    anthropic_last_test_date = models.DateTimeField(null=True, blank=True, help_text="Date when Anthropic AI configuration was last tested")
    anthropic_test_error = models.TextField(blank=True, null=True, help_text="Last Anthropic AI test error message if any")
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "Global Admin Settings"
        verbose_name_plural = "Global Admin Settings"
    
    def __str__(self):
        return "Global Admin Settings"
    
    def clean(self):
        """Validate model fields"""
        from django.core.exceptions import ValidationError
        from django.utils.html import strip_tags
        import re
        

        

    
    def save(self, *args, **kwargs):
        """Override save to update Django settings when OAuth/SCORM credentials are changed"""
        super().save(*args, **kwargs)
        
        # Update Django settings for backward compatibility
        try:
            from django.conf import settings as django_settings
            
            # Update Google OAuth settings
            if self.google_client_id and self.google_client_secret:
                django_settings.GOOGLE_OAUTH_CLIENT_ID = self.google_client_id
                django_settings.GOOGLE_OAUTH_CLIENT_SECRET = self.google_client_secret
            else:
                # Reset to environment values when not configured
                import os
                django_settings.GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
                django_settings.GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
            
            # SCORM Cloud settings are now handled by branch-specific SCORMIntegration model
            # SCORM settings are now branch-specific
                    
        except Exception:
            # Silently fail if settings update doesn't work
            pass
    
    def get_email_backend(self):
        """Get configured email backend for SMTP"""
        if not self.smtp_enabled or not self.smtp_host:
            return None
            
        from django.core.mail.backends.smtp import EmailBackend
        return EmailBackend(
            host=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_username,
            password=self.smtp_password,
            use_tls=self.smtp_use_tls,
            use_ssl=self.smtp_use_ssl,
        )
    
    def get_from_email(self):
        """Get formatted from email with display name"""
        if not self.smtp_enabled or not self.smtp_from_email:
            return None
            
        if self.smtp_from_name:
            return f"{self.smtp_from_name} <{self.smtp_from_email}>"
        return self.smtp_from_email
    
    def test_smtp_connection(self):
        """Test the SMTP configuration"""
        if not self.smtp_enabled or not self.smtp_host:
            return False, "SMTP is not enabled or configured"
            
        try:
            backend = self.get_email_backend()
            if not backend:
                return False, "Failed to create email backend"
                
            connection_opened = backend.open()
            if connection_opened:
                # Test actual authentication by trying to send a test email
                try:
                    from django.core.mail import EmailMessage
                    from django.utils import timezone
                    
                    # Create a test message to verify authentication
                    # We'll use a non-existent domain to avoid actually sending
                    test_msg = EmailMessage(
                        subject="SMTP Authentication Test",
                        body="This is a test message to verify SMTP authentication.",
                        from_email=self.get_from_email(),
                        to=['test@test-domain-that-does-not-exist.invalid'],
                        connection=backend
                    )
                    
                    # Try to prepare the message for sending - this will test authentication
                    # but since the domain is invalid, it won't actually send
                    try:
                        # This will trigger authentication but fail at delivery due to invalid domain
                        test_msg.send(fail_silently=False)
                    except Exception as send_error:
                        # Check if it's an authentication error vs delivery error
                        send_error_str = str(send_error).lower()
                        if any(auth_term in send_error_str for auth_term in 
                               ['530', '535', 'authentication', 'unauthorized', 'login', 'password']):
                            # This is an authentication error - re-raise it
                            raise send_error
                        else:
                            # This is likely a delivery error (expected with invalid domain)
                            # If we get here, authentication worked but delivery failed (which is expected)
                            pass
                    
                    # If we get here, authentication succeeded
                    backend.close()
                    self.smtp_is_tested = True
                    self.smtp_last_test_date = timezone.now()
                    self.smtp_test_error = ""
                    self.save(update_fields=['smtp_is_tested', 'smtp_last_test_date', 'smtp_test_error'])
                    return True, "SMTP connection and authentication successful"
                    
                except Exception as auth_error:
                    try:
                        backend.close()
                    except:
                        pass  # Ignore close errors
                    
                    # Handle authentication-specific errors
                    error_msg = str(auth_error)
                    formatted_error = self._format_smtp_auth_error(error_msg)
                    
                    self.smtp_is_tested = False
                    self.smtp_test_error = formatted_error
                    self.save(update_fields=['smtp_is_tested', 'smtp_test_error'])
                    return False, formatted_error
            else:
                error_msg = "Failed to establish SMTP connection"
                self.smtp_is_tested = False
                self.smtp_test_error = error_msg
                self.save(update_fields=['smtp_is_tested', 'smtp_test_error'])
                return False, error_msg
                
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_smtp_auth_error(error_msg)
            
            self.smtp_is_tested = False
            self.smtp_test_error = formatted_error
            self.save(update_fields=['smtp_is_tested', 'smtp_test_error'])
            return False, formatted_error
    
    def _format_smtp_auth_error(self, error_msg):
        """Format SMTP authentication error messages for better user understanding"""
        error_lower = error_msg.lower()
        
        # Microsoft 365/Office 365 specific errors
        if "5.7.139" in error_msg or "Session defaults policy" in error_lower:
            return (
                f" Microsoft 365 Session Error: {error_msg}\n\n"
                " SOLUTION STEPS:\n"
                "1. DISABLE Session Defaults (Most Important!):\n"
                "   • Go to https://entra.microsoft.com\n"
                "   • Navigate to Identity > Properties\n"
                "   • Click 'Manage Session defaults'\n"
                "   • Set 'Session defaults' to DISABLED\n"
                "   • Save changes\n\n"
                "2. If still failing, try App Password:\n"
                "   • Go to Microsoft Account Session settings\n"
                "   • Generate an App Password\n"
                "   • Use the App Password instead of your regular password\n\n"
                "3. Alternative: Use Microsoft Graph API (Recommended for production)\n\n"
                " Session Defaults blocks SMTP AUTH even when enabled per-user!"
            )
        
        # Gmail specific errors
        elif "gmail.com" in error_lower and ("535" in error_msg or "authentication" in error_lower):
            return (
                f" Gmail Authentication Error: {error_msg}\n\n"
                " SOLUTION STEPS:\n"
                "1. Enable 'Less secure app access' in Gmail settings\n"
                "2. OR generate an App Password if 2FA is enabled:\n"
                "   • Go to Google Account settings\n"
                "   • Session > 2-Step Verification > App passwords\n"
                "   • Generate password for 'Mail'\n"
                "   • Use this App Password instead of your regular password\n\n"
                "3. Verify SMTP settings:\n"
                "   • Host: smtp.gmail.com\n"
                "   • Port: 587 (TLS) or 465 (SSL)\n"
                "   • Username: your full Gmail address"
            )
        
        # Generic authentication errors
        elif any(term in error_lower for term in ['535', '530', 'authentication', 'login', 'password']):
            return (
                f" SMTP Authentication Failed: {error_msg}\n\n"
                " TROUBLESHOOTING STEPS:\n"
                "1. Verify username and password are correct\n"
                "2. Check if your email provider requires:\n"
                "   • App-specific passwords\n"
                "   • 'Less secure apps' to be enabled\n"
                "   • Two-factor authentication setup\n"
                "3. Confirm SMTP server settings:\n"
                "   • Correct hostname and port\n"
                "   • Proper encryption (TLS/SSL) settings\n"
                "4. Check with your email provider's documentation"
            )
        
        # Connection errors
        elif any(term in error_lower for term in ['connection', 'timeout', 'refused', 'unreachable']):
            return (
                f" SMTP Connection Error: {error_msg}\n\n"
                " TROUBLESHOOTING STEPS:\n"
                "1. Verify SMTP server hostname is correct\n"
                "2. Check port number (common ports: 25, 587, 465)\n"
                "3. Verify firewall/network settings allow SMTP traffic\n"
                "4. Try different encryption settings (TLS vs SSL)\n"
                "5. Contact your email provider or IT administrator"
            )
        
        # Return original error if no specific pattern matches
        return f" SMTP Error: {error_msg}"
    
    def test_anthropic_ai_connection(self):
        """Test the Anthropic AI configuration"""
        if not self.anthropic_ai_enabled or not self.anthropic_api_key:
            return False, "Anthropic AI is not enabled or API key is missing"
        
        try:
            from django.utils import timezone
            import requests
            import json
            
            # Check API key format
            if not self.anthropic_api_key.startswith('sk-ant-'):
                error_msg = "Invalid Anthropic API key format - should start with 'sk-ant-'"
                self.anthropic_is_tested = False
                self.anthropic_test_error = error_msg
                self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
                return False, error_msg
            
            # Test the connection by making a simple API request
            test_prompt = "Generate a brief test message to verify API connectivity."
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.anthropic_api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': self.anthropic_model,
                    'max_tokens': min(100, self.anthropic_max_tokens),  # Use small token limit for test
                    'messages': [
                        {
                            'role': 'user',
                            'content': test_prompt
                        }
                    ]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                # Check if response contains expected content
                try:
                    result = response.json()
                    content = result.get('content', [])
                    if content and content[0].get('type') == 'text':
                        # Connection successful
                        self.anthropic_is_tested = True
                        self.anthropic_last_test_date = timezone.now()
                        self.anthropic_test_error = ""
                        self.save(update_fields=['anthropic_is_tested', 'anthropic_last_test_date', 'anthropic_test_error'])
                        return True, "Anthropic AI connection successful and content generation verified"
                    else:
                        error_msg = "API responded but no text content was generated"
                        self.anthropic_is_tested = False
                        self.anthropic_test_error = error_msg
                        self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
                        return False, error_msg
                except json.JSONDecodeError:
                    error_msg = "Invalid JSON response from Anthropic API"
                    self.anthropic_is_tested = False
                    self.anthropic_test_error = error_msg
                    self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
                    return False, error_msg
            else:
                # Handle specific error cases
                error_msg = f"Anthropic API returned status {response.status_code}"
                if response.status_code == 401:
                    error_msg += " - Invalid API key or authentication failed"
                elif response.status_code == 429:
                    error_msg += " - Rate limit exceeded, try again later"
                elif response.status_code == 400:
                    error_msg += " - Bad request, check model and parameters"
                else:
                    try:
                        error_response = response.json()
                        if 'error' in error_response and 'message' in error_response['error']:
                            error_msg += f" - {error_response['error']['message']}"
                    except:
                        pass  # Use generic error message
                
                self.anthropic_is_tested = False
                self.anthropic_test_error = error_msg
                self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = "Connection timeout - Anthropic API did not respond within 30 seconds"
            self.anthropic_is_tested = False
            self.anthropic_test_error = error_msg
            self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
            return False, error_msg
        except requests.exceptions.ConnectionError:
            error_msg = "Connection error - Unable to reach Anthropic API"
            self.anthropic_is_tested = False
            self.anthropic_test_error = error_msg
            self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during Anthropic AI test: {str(e)}"
            self.anthropic_is_tested = False
            self.anthropic_test_error = error_msg
            self.save(update_fields=['anthropic_is_tested', 'anthropic_test_error'])
            return False, error_msg
    
    
    @classmethod
    def get_settings(cls):
        """Get or create global admin settings"""
        settings, created = cls.objects.get_or_create(id=1)
        return settings

class MenuControlSettings(models.Model):
    """Settings for controlling menu visibility across different roles"""
    
    # Menu sections that can be controlled
    MENU_SECTIONS = [
        ('dashboard', 'Dashboard'),
        ('user_management', 'User Management'),
        ('branch_portal', 'Branch Portal'),
        ('courses', 'Courses'),
        ('assignments', 'Assignments'),
        ('communication', 'Communication'),
        ('calendar', 'Calendar'),
        ('reports', 'Reports'),
        ('certificates', 'Certificates'),
        ('role_management', 'Role Management'),
        ('account_settings', 'Account & Settings'),
        ('subscription', 'Subscription'),
    ]
    
    # Sub-menu items
    SUBMENU_ITEMS = [
        # User Management submenus
        ('branches', 'Branches'),
        ('groups', 'Groups'),
        ('users', 'Users'),
        # Branch Portal submenus
        ('branch_dashboard', 'Branch Dashboard'),
        ('order_management', 'Order Management'),
        # Courses submenus
        ('course_list', 'Course List'),
        ('categories', 'Categories'),
        ('outcomes', 'Outcomes'),
        # Communication submenus
        ('messages', 'Messages'),
        ('discussions', 'Discussions'),
        ('conferences', 'Conferences'),
        ('notifications', 'Notifications'),
        # Reports submenus
        ('reports_overview', 'Reports Overview'),
        ('user_reports', 'User Reports'),
        ('group_reports', 'Group Reports'),
        ('branch_reports', 'Branch Reports'),
        ('course_reports', 'Course Reports'),
        ('learning_activities', 'Learning Activities'),
        ('training_matrix', 'Training Matrix'),
        ('gradebook', 'Gradebook'),
        ('timeline', 'Timeline'),
        ('custom_reports', 'Custom Reports'),
    ]
    
    menu_section = models.CharField(max_length=50, choices=MENU_SECTIONS)
    submenu_item = models.CharField(max_length=50, choices=SUBMENU_ITEMS, blank=True, null=True)
    
    # Role visibility
    visible_to_globaladmin = models.BooleanField(default=True)
    visible_to_superadmin = models.BooleanField(default=True)
    visible_to_admin = models.BooleanField(default=True)
    visible_to_instructor = models.BooleanField(default=True)
    visible_to_learner = models.BooleanField(default=True)
    
    # Custom roles
    visible_to_custom_roles = models.ManyToManyField('role_management.Role', blank=True, 
                                                   limit_choices_to={'name': 'custom'})
    
    # Settings
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ['menu_section', 'submenu_item']
        verbose_name = "Menu Control Setting"
        verbose_name_plural = "Menu Control Settings"
        ordering = ['menu_section', 'submenu_item']
    
    def __str__(self):
        if self.submenu_item:
            return f"{self.get_menu_section_display()} > {self.get_submenu_item_display()}"
        return self.get_menu_section_display()
    
    def is_visible_to_role(self, role_name):
        """Check if this menu item is visible to a specific role"""
        if not self.is_active:
            return False
            
        visibility_map = {
            'globaladmin': self.visible_to_globaladmin,
            'superadmin': self.visible_to_superadmin,
            'admin': self.visible_to_admin,
            'instructor': self.visible_to_instructor,
            'learner': self.visible_to_learner,
        }
        
        return visibility_map.get(role_name, False)
    
    @classmethod
    def initialize_default_settings(cls):
        """Initialize default menu control settings"""
        default_settings = [
            # Main menu sections
            ('dashboard', None, True, True, True, True, True),
            ('user_management', None, True, True, True, False, False),
            ('branch_portal', None, True, True, True, False, False),
            ('courses', None, True, True, True, True, True),
            ('assignments', None, True, True, True, True, True),
            ('communication', None, True, True, True, True, True),
            ('calendar', None, True, True, True, True, True),
            ('reports', None, True, True, True, True, False),
            ('certificates', None, True, True, True, True, True),
            ('role_management', None, True, True, True, False, False),
            ('account_settings', None, True, True, True, True, True),
            ('subscription', None, True, True, False, False, False),
            
            # User Management submenus
            ('user_management', 'branches', True, True, False, False, False),
            ('user_management', 'groups', True, True, True, False, False),
            ('user_management', 'users', True, True, True, False, False),
            
            # Communication submenus
            ('communication', 'messages', True, True, True, True, True),
            ('communication', 'discussions', True, True, True, True, True),
            ('communication', 'conferences', True, True, True, True, True),
            ('communication', 'notifications', True, True, True, True, True),
            
            # Reports submenus
            ('reports', 'reports_overview', True, True, True, True, False),
            ('reports', 'user_reports', True, True, True, False, False),
            ('reports', 'group_reports', True, True, True, False, False),
            ('reports', 'branch_reports', True, True, False, False, False),
            ('reports', 'course_reports', True, True, True, True, False),
            ('reports', 'learning_activities', True, True, True, True, False),
            ('reports', 'training_matrix', True, True, True, True, False),
            ('reports', 'gradebook', True, True, True, True, False),
            ('reports', 'timeline', True, True, True, True, False),
            ('reports', 'custom_reports', True, True, True, False, False),
        ]
        
        for setting in default_settings:
            menu_section, submenu_item, global_vis, super_vis, admin_vis, instr_vis, learn_vis = setting
            cls.objects.get_or_create(
                menu_section=menu_section,
                submenu_item=submenu_item,
                defaults={
                    'visible_to_globaladmin': global_vis,
                    'visible_to_superadmin': super_vis,
                    'visible_to_admin': admin_vis,
                    'visible_to_instructor': instr_vis,
                    'visible_to_learner': learn_vis,
                    'is_active': True
                }
            )

class AIControlSettings(models.Model):
    """Settings for AI features control"""
    
    AI_FEATURES = [
        ('lesson_planning', 'AI Lesson Planning'),
        ('assessment_generation', 'AI Assessment Generation'),
        ('automatic_grading', 'AI Automatic Grading'),
        ('personal_tutor', 'AI Personal Tutor'),
        ('content_recommendation', 'AI Content Recommendation'),
        ('chatbot_support', 'AI Chatbot Support'),
        ('plagiarism_detection', 'AI Plagiarism Detection'),
        ('analytics_insights', 'AI Analytics Insights'),
    ]
    
    feature_name = models.CharField(max_length=50, choices=AI_FEATURES, unique=True)
    is_enabled = models.BooleanField(default=False, help_text="Enable this AI feature system-wide")
    is_beta = models.BooleanField(default=True, help_text="Mark this feature as beta")
    
    # Configuration
    api_endpoint = models.URLField(blank=True, null=True, help_text="API endpoint for this AI service")
    api_key = models.CharField(max_length=255, blank=True, null=True, help_text="API key for AI service")
    model_version = models.CharField(max_length=100, blank=True, null=True, help_text="AI model version")
    
    # Usage limits
    daily_usage_limit = models.IntegerField(default=1000, help_text="Daily usage limit for this feature")
    monthly_usage_limit = models.IntegerField(default=30000, help_text="Monthly usage limit for this feature")
    
    # Role permissions
    available_to_globaladmin = models.BooleanField(default=True)
    available_to_superadmin = models.BooleanField(default=True)
    available_to_admin = models.BooleanField(default=False)
    available_to_instructor = models.BooleanField(default=False)
    available_to_learner = models.BooleanField(default=False)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "AI Control Setting"
        verbose_name_plural = "AI Control Settings"
        ordering = ['feature_name']
    
    def __str__(self):
        status = "Enabled" if self.is_enabled else "Disabled"
        beta = " (Beta)" if self.is_beta else ""
        return f"{self.get_feature_name_display()} - {status}{beta}"
    
    def is_available_to_role(self, role_name):
        """Check if this AI feature is available to a specific role"""
        if not self.is_enabled:
            return False
            
        availability_map = {
            'globaladmin': self.available_to_globaladmin,
            'superadmin': self.available_to_superadmin,
            'admin': self.available_to_admin,
            'instructor': self.available_to_instructor,
            'learner': self.available_to_learner,
        }
        
        return availability_map.get(role_name, False)
    
    @classmethod
    def initialize_default_features(cls):
        """Initialize default AI control settings"""
        default_features = [
            ('lesson_planning', False, True, True, True, False, False, False),
            ('assessment_generation', False, True, True, True, False, False, False),
            ('automatic_grading', False, True, True, True, False, False, False),
            ('personal_tutor', False, True, True, False, False, False, True),
            ('content_recommendation', False, True, True, False, False, False, True),
            ('chatbot_support', False, True, True, False, False, False, True),
            ('plagiarism_detection', False, True, True, True, False, False, False),
            ('analytics_insights', False, True, True, True, False, False, False),
        ]
        
        for feature in default_features:
            feature_name, enabled, beta, global_av, super_av, admin_av, instr_av, learn_av = feature
            cls.objects.get_or_create(
                feature_name=feature_name,
                defaults={
                    'is_enabled': enabled,
                    'is_beta': beta,
                    'available_to_globaladmin': global_av,
                    'available_to_superadmin': super_av,
                    'available_to_admin': admin_av,
                    'available_to_instructor': instr_av,
                    'available_to_learner': learn_av,
                }
            )
