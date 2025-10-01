from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
import uuid
import logging
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
import json
from users.models import CustomUser
from .utils.api import SCORMCloudAPI, SCORMCloudError

logger = logging.getLogger(__name__)

# Define authentication types
AUTH_TYPES = [
    ('cookies', 'Cookie Based'),
    ('url', 'URL Parameters'),
    ('form', 'Form Post'),
    ('basic', 'HTTP Basic'),
    ('oauth', 'OAuth')
]

def get_topic_model():
    return apps.get_model('courses', 'Topic')

def get_topic_progress_model():
    return apps.get_model('courses', 'TopicProgress')

def get_topic_course(topic):
    """Helper function to get course for a topic through CourseTopic"""
    from courses.models import Course
    return Course.objects.filter(coursetopic__topic=topic).first()

class SCORMDestination(models.Model):
    """Model for SCORM Cloud destinations"""
    name = models.CharField(max_length=255)
    cloud_id = models.CharField(max_length=255, unique=True, blank=True)
    auth_type = models.CharField(max_length=50, choices=AUTH_TYPES, default='cookies')
    hash_user_info = models.BooleanField(default=False)
    additional_settings = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Validate the model data"""
        if not self.name or len(self.name.strip()) < 3:
            raise ValidationError({'name': 'Name must be at least 3 characters long'})
            
        if self.cloud_id:
            if not self.cloud_id.startswith('d_'):
                self.cloud_id = f'd_{self.cloud_id}'
        
        super().clean()

    def save(self, *args, **kwargs):
        """Save with automatic cloud_id generation and SCORM Cloud destination creation"""
        sync_with_cloud = kwargs.pop('sync_with_cloud', True)
        
        # Generate a cloud ID if none exists
        if not self.cloud_id:
            self.cloud_id = f"d_{uuid.uuid4().hex[:8]}"
        
        # Ensure cloud_id has proper prefix
        if not self.cloud_id.startswith('d_') and self.cloud_id != 'default_lms_destination':
            self.cloud_id = f"d_{self.cloud_id}"
        
        # Clean up the name field
        if self.name:
            self.name = self.name.strip()
        
        # If sync_with_cloud is False, just save to database without SCORM Cloud sync
        if not sync_with_cloud:
            return super().save(*args, **kwargs)
            
        # Sync with SCORM Cloud
        from .utils.api import get_scorm_client
        
        try:
            # Get SCORM client
            scorm_cloud = get_scorm_client()
            if not scorm_cloud:
                logger.warning(f"No SCORM client available for destination {self.cloud_id}, saving locally only")
                return super().save(*args, **kwargs)
            
            # First check if this destination already exists
            try:
                # Try to get the destination from SCORM Cloud
                destination = scorm_cloud.get_destination(self.cloud_id)
                if destination:
                    logger.info(f"Found existing destination {self.cloud_id}")
            except Exception as e:
                # If destination not found or error occurs, create a new one
                logger.info(f"Creating new destination with data: {{\n  \"destinations\": [\n    {{\n      \"id\": \"{self.cloud_id}\",\n      \"name\": \"{self.name}\",\n      \"data\": {{\n        \"name\": \"{self.name}\",\n        \"launchAuth\": {{\n          \"type\": \"{self.auth_type}\",\n          \"options\": {{}}\n        }},\n        \"hashUserInfo\": {str(self.hash_user_info).lower()},\n        \"tags\": []\n      }}\n    }}\n  ]\n}}")
                
                try:
                    # Create the destination in SCORM Cloud
                    destination_data = {
                        "destinations": [
                            {
                                "id": self.cloud_id,
                                "name": self.name,
                                "data": {
                                    "name": self.name,
                                    "launchAuth": {
                                        "type": self.auth_type,
                                        "options": {}
                                    },
                                    "hashUserInfo": self.hash_user_info,
                                    "tags": []
                                }
                            }
                        ]
                    }
                    
                    destination_response = scorm_cloud.create_destination(destination_data)
                    if not destination_response:
                        logger.warning("Failed to create destination in SCORM Cloud")
                except Exception as dest_error:
                    logger.error(f"Error saving destination: {str(dest_error)}")
                    logger.warning("Continuing with local save despite SCORM Cloud error")
        except Exception as e:
            logger.error(f"Error in destination save process: {str(e)}")
            logger.warning("Continuing with local save despite SCORM Cloud error")
        
        # Save to the database
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class SCORMDispatch(models.Model):
    """Links a SCORM package to a destination for delivery"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destination = models.ForeignKey(
        SCORMDestination, 
        on_delete=models.CASCADE,
        related_name='dispatches'
    )
    package = models.ForeignKey(
        'SCORMPackage',
        on_delete=models.CASCADE,
        related_name='dispatches'
    )
    cloud_id = models.CharField(max_length=255, unique=True)
    
    # Status Fields
    enabled = models.BooleanField(default=True)
    allow_new_registrations = models.BooleanField(default=True)
    registration_cap = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Maximum number of registrations allowed"
    )
    
    # Registration Management
    registration_count = models.IntegerField(default=0)
    last_reset_date = models.DateTimeField(null=True, blank=True)
    expiration_date = models.DateTimeField(null=True, blank=True)
    
    # Progress Tracking
    instanced = models.BooleanField(
        default=True,
        help_text="Enable versioning support"
    )
    
    # Additional Data
    notes = models.TextField(blank=True)
    tracking_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'SCORM Dispatch'
        verbose_name_plural = 'SCORM Dispatches'
        unique_together = ['destination', 'package']
        ordering = ['-updated_at']

    def __str__(self):
        return f"Dispatch {self.cloud_id} - {self.package.title}"

    def save(self, *args, **kwargs):
        from .utils.api import get_scorm_client
        
        if not self.cloud_id:
            self.cloud_id = f"D_{uuid.uuid4().hex[:8]}"
            
        # Create or update in SCORM Cloud
        if not self.pk:
            # New dispatch - create in SCORM Cloud
            scorm_cloud = get_scorm_client()
            if scorm_cloud and scorm_cloud.is_configured:
                try:
                    dispatch = scorm_cloud._create_dispatch(
                        self.package.cloud_id,
                        self.destination.cloud_id
                    )
                    if not dispatch:
                        logger.warning("Failed to create dispatch in SCORM Cloud")
                except Exception as e:
                    logger.warning(f"Error creating dispatch in SCORM Cloud: {str(e)}")
        else:
            # Existing dispatch - update in SCORM Cloud
            scorm_cloud = get_scorm_client()
            if scorm_cloud and scorm_cloud.is_configured:
                try:
                    dispatch = scorm_cloud.update_dispatch(
                        self.cloud_id,
                        enabled=self.enabled,
                        allow_new_registrations=self.allow_new_registrations
                    )
                    if not dispatch:
                        logger.warning("Failed to update dispatch in SCORM Cloud")
                except Exception as e:
                    logger.warning(f"Error updating dispatch in SCORM Cloud: {str(e)}")
                
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from .utils.api import get_scorm_client
        
        # Delete from SCORM Cloud
        if self.cloud_id:
            scorm_cloud = get_scorm_client()  # No user context available
            if scorm_cloud and scorm_cloud.is_configured:
                try:
                    scorm_cloud.delete_dispatch(self.cloud_id)
                except Exception as e:
                    logger.warning(f"Error deleting dispatch from SCORM Cloud: {str(e)}")
            
        super().delete(*args, **kwargs)

    def get_launch_url(self, registration):
        """Get launch URL for a specific registration"""
        from .utils.api import get_scorm_client
        
        try:
            scorm_cloud = get_scorm_client()
            if scorm_cloud and scorm_cloud.is_configured:
                return scorm_cloud.get_dispatch_launch_url(
                    self.cloud_id,
                    registration.registration_id
                )
            else:
                logger.warning("SCORM Cloud not configured")
                return None
        except Exception as e:
            logger.error(f"Error getting dispatch launch URL: {str(e)}")
            return None

    def reset_registration_count(self):
        """Reset the registration counter"""
        from .utils.api import get_scorm_client
        
        try:
            scorm_cloud = get_scorm_client()  # No user context available
            scorm_cloud.reset_dispatch_registration_count(self.cloud_id)
            self.registration_count = 0
            self.last_reset_date = timezone.now()
            self.save()
            return True
        except Exception as e:
            logger.error(f"Error resetting registration count: {str(e)}")
            return False

    def sync_with_cloud(self):
        """Sync dispatch with SCORM Cloud"""
        from .utils.api import get_scorm_client
        
        try:
            cloud_dispatch = scorm_cloud.get_dispatch(self.cloud_id)
            if cloud_dispatch:
                self.enabled = cloud_dispatch.get('enabled', True)
                self.allow_new_registrations = cloud_dispatch.get('allowNewRegistrations', True)
                self.registration_count = cloud_dispatch.get('registrationCount', 0)
                self.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Error syncing dispatch: {str(e)}")
            return False

class SCORMPackage(models.Model):
    """SCORM Package in Cloud Storage"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cloud_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(
        max_length=50,
        choices=[
            ('1.2', 'SCORM 1.2'),
            ('2004', 'SCORM 2004')
        ],
        default='1.2'
    )
    upload_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    launch_url = models.URLField(max_length=1000)
    entry_url = models.URLField(max_length=1000, blank=True)
    
    # Launch presentation settings
    use_frameset = models.BooleanField(default=True, help_text="Use frameset instead of iframe")
    launch_mode = models.CharField(
        max_length=20,
        choices=[
            ('iframe', 'Embed in iframe'),
            ('window', 'Open in same window'),
            ('popup', 'Open in popup window')
        ],
        default='window',
        help_text="How to open SCORM content"
    )

    # Added field for default destination
    default_destination = models.ForeignKey(
        'SCORMDestination',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_packages'
    )

    class Meta:
        verbose_name = 'SCORM Package'
        verbose_name_plural = 'SCORM Packages'

    def __str__(self):
        return f"{self.title} ({self.version})"

    def get_launch_url(self):
        """Get launch URL with proper SCORM API initialization"""
        from .utils.api import get_scorm_client
        
        # Get branch-specific SCORM client (no user context available in this method)
        scorm_cloud = get_scorm_client()
        try:
            # Create a test registration if needed
            registration_id = f"preview_{self.cloud_id}"
            
            # Create registration data
            registration_data = {
                "courseId": self.cloud_id,
                "registrationId": registration_id,
                "learner": {
                    "id": registration_id
                }
            }
            
            # Create or get registration
            try:
                scorm_cloud._make_request('POST', 'registrations', data=registration_data)
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    raise
            
            # Get launch URL with proper configuration based on package settings
            # Always use frameset mode regardless of package settings
            additional_settings = {
                'embedded': False,  # Always false for frameset
                'api': True,
                'initializeApi': True,
                'framesetSupport': True,  # Always enable frameset support
                'configuration': {
                    'scoLaunchType': 'frameset',  # Always use frameset
                    'apiPlacementStrategy': 'top',  # Required for frameset
                    'apiLocation': 'top',  # Required for frameset
                    'targetWindow': '_self' if self.launch_mode == 'window' else 
                                  ('_blank' if self.launch_mode == 'popup' else '_self'),
                    'playerConfiguration': {
                        'height': '100%',
                        'width': '100%',
                        'displayStandalone': True,  # Required for frameset
                        'forceReview': False,
                        'showProgressBar': True,
                        'showNavBar': True,
                        'lmsEnabled': True,
                        'apiEnabled': True,
                        'autoProgress': True,
                        'logLevel': 5,
                        'debugEnabled': True
                    }
                }
            }
            
            # Get the launch URL through the API method that uses POST
            # rather than trying to access the preview URL directly
            launch_url = scorm_cloud.build_launch_link(
                registration_id,
                additional_settings=additional_settings
            )
            
            return launch_url
            
        except Exception as e:
            logger.error(f"Error getting launch URL for package {self.cloud_id}: {str(e)}")
            return None

    def regenerate_launch_url(self):
        """Regenerate launch URL for the package"""
        launch_url = self.get_launch_url()
        if launch_url:
            self.launch_url = launch_url
            self.save()
            return True
        return False

    def get_registration(self, user):
        """Get or create registration for user with proper SCORM Cloud integration"""
        from .utils.api import get_scorm_client
        
        try:
            # First try to get existing registration
            registration = SCORMRegistration.objects.filter(
                package=self,
                user=user
            ).first()
            
            if registration:
                logger.info(f"Found existing registration for user {user.username}")
                return registration
            
            # Create new registration
            registration_id = f"LMS_{uuid.uuid4().hex}"
            logger.info(f"Creating new registration {registration_id} for user {user.username}")
            
            # Get branch-specific SCORM client
            scorm_cloud = get_scorm_client(user=user, branch=user.branch if hasattr(user, 'branch') else None)
            
            # Create registration in SCORM Cloud using the package's cloud_id as course ID
            cloud_response = scorm_cloud.create_registration(
                course_id=self.cloud_id,  # This is the course ID from the package
                learner_id=str(user.id),
                registration_id=registration_id
            )
            
            if cloud_response:
                # Create local registration record
                registration = SCORMRegistration.objects.create(
                    package=self,
                    user=user,
                    registration_id=registration_id
                )
                
                logger.info(f"Successfully created registration {registration_id}")
                return registration
            
            logger.error("Failed to create registration in SCORM Cloud")
            return None
            
        except Exception as e:
            logger.error(f"Error in get_registration: {str(e)}")
            return None

    def get_or_create_dispatch(self, destination=None):
        """Get or create dispatch for this package"""
        from .utils.api import get_scorm_client, SCORMCloudError
        
        try:
            # Use provided destination or get/create default
            destination_to_use = destination
            
            if not destination_to_use:
                # Try to get existing default destination
                destination_to_use = self.default_destination
                
                # If no default destination, try to find a suitable one
                if not destination_to_use:
                    # Look for any existing destination
                    existing_destinations = SCORMDestination.objects.all().first()
                    if existing_destinations:
                        destination_to_use = existing_destinations
                        # Set as default for this package
                        self.default_destination = destination_to_use
                        self.save(update_fields=['default_destination'])
                        logger.info(f"Using existing destination {destination_to_use.cloud_id} as default for package {self.cloud_id}")
                
                # If still no destination, create a new default one
                if not destination_to_use:
                    logger.info(f"Creating new default destination for package {self.cloud_id}")
                    
                    # Generate unique destination ID
                    destination_id = f"d_default_{uuid.uuid4().hex[:8]}"
                    destination_name = f"Default LMS Destination"
                    
                    try:
                        # First create in SCORM Cloud
                        destination_data = {
                            "destinations": [
                                {
                                    "id": destination_id,
                                    "name": destination_name,
                                    "data": {
                                        "name": destination_name,
                                        "launchAuth": {
                                            "type": "cookies",
                                            "options": {}
                                        },
                                        "hashUserInfo": False,
                                        "tags": []
                                    }
                                }
                            ]
                        }
                        
                        destination_response = scorm_cloud.create_destination(destination_data)
                        if not destination_response:
                            logger.warning("Failed to create destination in SCORM Cloud, proceeding with local destination")
                        
                        # Create destination model object (even if SCORM Cloud creation failed)
                        destination_to_use = SCORMDestination.objects.create(
                            cloud_id=destination_id,
                            name=destination_name,
                            auth_type='cookies',
                            hash_user_info=False
                        )
                        
                        # Set as default for this package
                        self.default_destination = destination_to_use
                        self.save(update_fields=['default_destination'])
                        
                        logger.info(f"Created new default destination {destination_id} for package {self.cloud_id}")
                        
                    except Exception as dest_error:
                        logger.error(f"Error creating destination: {str(dest_error)}")
                        # Create a minimal destination anyway
                        try:
                            destination_to_use = SCORMDestination.objects.create(
                                cloud_id=destination_id,
                                name=destination_name,
                                auth_type='cookies',
                                hash_user_info=False
                            )
                            self.default_destination = destination_to_use
                            self.save(update_fields=['default_destination'])
                            logger.info(f"Created local-only destination {destination_id} as fallback")
                        except Exception as fallback_error:
                            logger.error(f"Could not create even local destination: {str(fallback_error)}")
                            return None
            
            # Validate destination
            if not destination_to_use or not destination_to_use.cloud_id:
                logger.error(f"Invalid destination for dispatch: {destination_to_use}")
                return None
            
            # Check if dispatch already exists
            existing_dispatch = SCORMDispatch.objects.filter(
                package=self,
                destination=destination_to_use
            ).first()
            
            if existing_dispatch:
                logger.info(f"Found existing dispatch {existing_dispatch.cloud_id} for package {self.cloud_id}")
                return existing_dispatch
            
            # Generate dispatch ID
            dispatch_id = f"dis_{uuid.uuid4().hex[:8]}"
            
            # Try to create dispatch in SCORM Cloud
            try:
                # Prepare dispatch data
                dispatch_data = {
                    "dispatches": [
                        {
                            "id": dispatch_id,
                            "data": {
                                "courseId": self.cloud_id,
                                "destinationId": destination_to_use.cloud_id,
                                "allowNewRegistrations": True,
                                "registrationCount": 0,
                                "enabled": True,
                                "expirationDate": None
                            }
                        }
                    ]
                }
                
                # Create the dispatch
                logger.info(f"Creating dispatch {dispatch_id} in SCORM Cloud")
                dispatch_response = scorm_cloud._make_request('POST', f'dispatches', data=dispatch_data)
                
                if not dispatch_response:
                    logger.warning("No response when creating dispatch in SCORM Cloud, proceeding with local dispatch")
                else:
                    logger.info(f"Successfully created dispatch {dispatch_id} in SCORM Cloud")
                
            except Exception as cloud_error:
                logger.warning(f"Failed to create dispatch in SCORM Cloud: {str(cloud_error)}, proceeding with local dispatch")
            
            # Create dispatch model object (regardless of SCORM Cloud status)
            try:
                dispatch = SCORMDispatch.objects.create(
                    cloud_id=dispatch_id,
                    package=self,
                    destination=destination_to_use,
                    enabled=True,
                    registration_count=0,
                    allow_new_registrations=True
                )
                
                logger.info(f"Created dispatch record {dispatch_id} for package {self.cloud_id}")
                return dispatch
                
            except Exception as db_error:
                logger.error(f"Error creating dispatch database record: {str(db_error)}")
                return None
        
        except Exception as e:
            logger.error(f"Error getting or creating dispatch: {str(e)}")
            logger.exception("Dispatch creation error details:")
            return None

class SCORMCloudContent(models.Model):
    """SCORM Cloud content that can be linked to any type of content"""
    package = models.ForeignKey(
        SCORMPackage,
        on_delete=models.CASCADE,
        related_name='cloud_contents',
        null=True,
        blank=True,
        help_text="SCORM package associated with this content"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="External content identifier"
    )
    content_type = models.CharField(
        max_length=50,
        default='generic',
        help_text="Type of content this SCORM package is associated with"
    )
    registration_prefix = models.CharField(max_length=50, default='LMS_')
    passing_score = models.IntegerField(default=80)
    requires_passing_score = models.BooleanField(default=True)
    tracking_data = models.JSONField(default=dict, blank=True)
    
    # Add scorm_package_id field to handle SCORM Cloud package references
    scorm_package_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="SCORM Cloud package ID for direct reference"
    )

    class Meta:
        verbose_name = 'SCORM Cloud Content'
        verbose_name_plural = 'SCORM Cloud Contents'
        unique_together = [('content_type', 'content_id')]

    def __str__(self):
        return f"{self.title} ({self.content_type})"

    def sync_with_cloud(self):
        """Sync content with SCORM Cloud"""
        from .utils.api import get_scorm_client
        try:
            # Get course details from SCORM Cloud
            course = scorm_cloud._make_request('GET', f'courses/{self.package.cloud_id}')
            if course:
                self.title = course.get('title', self.title)
                self.description = course.get('description', self.description)
                self.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Error syncing SCORM Cloud content: {str(e)}")
            return False

    def get_launch_url(self, user):
        """Get launch URL for user with improved error handling and branch-specific support"""
        try:
            # Try to get package from either the foreign key or scorm_package_id field
            package = self.package
            if not package and self.scorm_package_id:
                # Try to find package by scorm_package_id
                try:
                    package = SCORMPackage.objects.filter(cloud_id=self.scorm_package_id).first()
                except Exception as e:
                    logger.error(f"Error finding package by scorm_package_id {self.scorm_package_id}: {str(e)}")
            
            if not package:
                logger.error(f"Cannot get launch URL for content {self.id}: No package associated")
                return None
                
            registration = package.get_registration(user)
            if not registration:
                logger.error(f"Cannot get launch URL for content {self.id}: No registration found for user {user.id}")
                return None
                
            # Get site URL for redirect
            from django.conf import settings
            redirect_url = getattr(settings, 'BASE_URL', None)
            if not redirect_url:
                # Fallback to BASE_URL from settings
                redirect_url = getattr(settings, 'BASE_URL', 
                                       f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}")
            
            launch_url = registration.get_launch_url(redirect_url=redirect_url)
            logger.info(f"Got launch URL for content {self.id}, user {user.id}: {launch_url}")
            return launch_url
            
        except Exception as e:
            logger.error(f"Error getting launch URL for content {self.id}, user {user.id}: {str(e)}", exc_info=True)
            return None

    def sync_progress(self, user):
        """Sync progress data for user"""
        # Try to get package from either the foreign key or scorm_package_id field
        package = self.package
        if not package and self.scorm_package_id:
            try:
                package = SCORMPackage.objects.filter(cloud_id=self.scorm_package_id).first()
            except Exception as e:
                logger.error(f"Error finding package by scorm_package_id {self.scorm_package_id}: {str(e)}")
        
        if not package:
            logger.error(f"Cannot sync progress for content {self.id}: No package associated")
            return False
            
        registration = package.get_registration(user)
        if registration:
            return registration.sync_completion_status()
        return False

    def get_progress_status(self, user):
        """Get formatted progress status with all relevant data"""
        # Try to get package from either the foreign key or scorm_package_id field
        package = self.package
        if not package and self.scorm_package_id:
            try:
                package = SCORMPackage.objects.filter(cloud_id=self.scorm_package_id).first()
            except Exception as e:
                logger.error(f"Error finding package by scorm_package_id {self.scorm_package_id}: {str(e)}")
        
        if not package:
            return {
                'status': 'not_attempted',
                'score': None,
                'total_time': 0,
                'completion_date': None,
                'launch_url': None
            }
            
        registration = package.get_registration(user)
        if not registration:
            return {
                'status': 'not_attempted',
                'score': None,
                'total_time': 0,
                'completion_date': None,
                'launch_url': None
            }

        return {
            'status': registration.completion_status,
            'score': float(registration.score) if registration.score else None,
            'total_time': registration.total_time,
            'completion_date': registration.completion_date,
            'launch_url': registration.get_launch_url()
        }

class SCORMRegistration(models.Model):
    """Model for SCORM Cloud registrations"""
    registration_id = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='scorm_registrations'
    )
    package = models.ForeignKey(
        SCORMPackage,
        on_delete=models.CASCADE,
        related_name='registrations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completion_status = models.CharField(max_length=20, default='incomplete')
    success_status = models.CharField(max_length=20, default='unknown')
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total_time = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    # Store registration data for faster access
    progress_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = 'SCORM Registration'
        verbose_name_plural = 'SCORM Registrations'
        
    def __str__(self):
        return f"{self.registration_id} - {self.user.username if self.user else 'No User'}"

    def get_course_id(self):
        """Get the course ID associated with this registration"""
        # First check if package has cloud_id
        if self.package and self.package.cloud_id:
            return self.package.cloud_id
            
        # If not found in package, try to get from SCORM Cloud API
        try:
            from .utils.api import get_scorm_client
            registration_data = scorm_cloud._make_request(
                'GET',
                f'registrations/{self.registration_id}'
            )
            
            if registration_data and 'courseId' in registration_data:
                # Store the course ID in the package for future use
                if self.package and not self.package.cloud_id:
                    self.package.cloud_id = registration_data['courseId']
                    self.package.save(update_fields=['cloud_id'])
                return registration_data['courseId']
        except Exception as e:
            logger.error(f"Error getting course ID for registration {self.registration_id}: {str(e)}")
            
        # Last resort - try to extract course ID from registration ID
        # Many registration IDs follow patterns like LMS_TOPIC_{course_id}
        if '_' in self.registration_id:
            parts = self.registration_id.split('_')
            if len(parts) >= 3 and parts[0] == 'LMS':
                # Check if the extracted ID exists as a course
                potential_id = '_'.join(parts[1:])
                try:
                    from .utils.api import get_scorm_client
                    course = scorm_cloud._make_request('GET', f'courses/{potential_id}')
                    if course and 'id' in course:
                        # Update package cloud_id for future
                        if self.package and not self.package.cloud_id:
                            self.package.cloud_id = potential_id
                            self.package.save(update_fields=['cloud_id'])
                        return potential_id
                except:
                    pass
                    
        # If we get here, we couldn't find a course ID
        logger.error(f"Unable to determine course ID for registration {self.registration_id}")
        return None

    def get_launch_url(self, redirect_url=None, additional_settings=None):
        """Get launch URL from SCORM Cloud with improved error handling and consistent behavior"""
        from .utils.api import get_scorm_client, SCORMCloudError
        
        try:
            if not self.registration_id:
                logger.error("Registration ID is missing")
                return None
                
            # Set redirect URL
            if not redirect_url:
                from django.conf import settings
                redirect_url = getattr(settings, 'BASE_URL', None)
                if not redirect_url:
                    # Fallback to BASE_URL from settings
                    redirect_url = getattr(settings, 'BASE_URL', 
                                           f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}")
            
            # Get branch-specific SCORM client
            scorm_cloud = get_scorm_client(user=self.user, branch=self.user.branch if hasattr(self.user, 'branch') else None)
            
            # Get launch URL from SCORM Cloud with proper configuration
            default_settings = {
                'embedded': False,  # Always false for frameset
                'api': True,
                'initializeApi': True,
                'framesetSupport': True,  # Always true for frameset
                'scormVersion': '1.2',
                'apiVersion': '1.2',
                'forceReview': False,
                'commitOnUnload': True,
                'apiCommitFrequency': 'auto',
                'apiLogFrequency': '1',
                'apiPostbackTimeout': 30000,
                'apiPostbackAttempts': 3,
                'preventFrameBust': True,
                'apiSandbox': False,
                'configuration': {
                    'scoLaunchType': 'frameset',  # Always use frameset launch type
                    'apiPlacementStrategy': 'top',  # Required for frameset
                    'apiLocation': 'top',  # Required for frameset
                    'apiStayInParent': False,
                    'targetWindow': '_self',
                    'playerConfiguration': {
                        'height': '100%',
                        'width': '100%',
                        'displayStandalone': True,  # Required for frameset
                        'forceReview': False,
                        'showProgressBar': True,
                        'showNavBar': True,
                        'lmsEnabled': True,
                        'apiEnabled': True,
                        'autoProgress': True,
                        'logLevel': 5,
                        'debugEnabled': True
                    }
                }
            }
            
            # Merge additional settings if provided
            if additional_settings:
                from .utils.api import SCORMCloudAPI
                # Use a temporary API instance for settings merging
                api = SCORMCloudAPI(app_id="temp", secret_key="temp")
                api._deep_merge_settings(default_settings, additional_settings)
            
            # Force frameset settings always
            default_settings['embedded'] = False
            default_settings['framesetSupport'] = True
            if 'configuration' in default_settings:
                default_settings['configuration']['scoLaunchType'] = 'frameset'
                default_settings['configuration']['apiPlacementStrategy'] = 'top'
                default_settings['configuration']['apiLocation'] = 'top'
                if 'playerConfiguration' in default_settings['configuration']:
                    default_settings['configuration']['playerConfiguration']['displayStandalone'] = True
            
            launch_url = scorm_cloud.build_launch_link(
                self.registration_id,
                redirect_on_exit_url=redirect_url,
                additional_settings=default_settings
            )
            
            # If we couldn't get a launch URL from registration, try direct content URL
            if not launch_url:
                # Get course ID from registration
                course_id = self.get_course_id()
                if course_id:
                    logger.info(f"Using direct content URL for course {course_id}")
                    launch_url = scorm_cloud.get_direct_launch_url(
                        course_id=course_id, 
                        redirect_url=redirect_url
                    )
            
            logger.info(f"Launch URL: {launch_url}")
            return launch_url
            
        except SCORMCloudError as e:
            logger.error(f"SCORM Cloud error: {str(e)}")
            # Try fallback preview URL
            try:
                if self.package and self.package.cloud_id:
                    logger.info(f"Trying fallback preview URL for {self.registration_id}")
                    preview_data = {"redirectOnExitUrl": redirect_url}
                    preview_response = scorm_cloud._make_request(
                        'POST',
                        f'courses/{self.package.cloud_id}/preview',
                        data=preview_data
                    )
                    
                    if preview_response and 'launchLink' in preview_response:
                        preview_url = preview_response['launchLink']
                        logger.info(f"Generated fallback preview URL: {preview_url}")
                        return preview_url
            except Exception as fallback_error:
                logger.error(f"Error generating fallback preview URL: {str(fallback_error)}")
            return None
        except Exception as e:
            logger.error(f"Error getting launch URL: {str(e)}")
            # Try fallback preview URL
            try:
                if self.package and self.package.cloud_id:
                    logger.info(f"Trying fallback preview URL for {self.registration_id}")
                    preview_data = {"redirectOnExitUrl": redirect_url}
                    preview_response = scorm_cloud._make_request(
                        'POST',
                        f'courses/{self.package.cloud_id}/preview',
                        data=preview_data
                    )
                    
                    if preview_response and 'launchLink' in preview_response:
                        preview_url = preview_response['launchLink']
                        logger.info(f"Generated fallback preview URL: {preview_url}")
                        return preview_url
            except Exception as fallback_error:
                logger.error(f"Error generating fallback preview URL: {str(fallback_error)}")
            return None

    def sync_completion_status(self):
        """Sync completion status from SCORM Cloud with improved error handling"""
        from .utils.api import get_scorm_client
        try:
            # Get branch-specific SCORM client
            scorm_cloud = get_scorm_client(user=self.user, branch=self.user.branch if hasattr(self.user, 'branch') else None)
            
            # Get registration data from SCORM Cloud
            data = scorm_cloud.get_registration_status(self.registration_id)
            if not data:
                logger.error(f"No data returned for registration {self.registration_id}")
                return False

            # Update completion status
            self.completion_status = data.get('registrationCompletion', 'unknown').lower()
            self.success_status = data.get('registrationSuccess', 'unknown').lower()
            
            # Normalize status values
            if self.completion_status == 'complete':
                self.completion_status = 'completed'
            
            # Update score using unified scoring service
            if 'score' in data:
                from core.utils.scoring import ScoreCalculationService
                
                score_data = data['score']
                normalized_score = ScoreCalculationService.handle_scorm_score(score_data)
                
                if normalized_score is not None:
                    self.score = normalized_score
                    logger.info(f"Updated registration score to: {normalized_score}")
            
            # Update time tracking
            if 'totalSecondsTracked' in data:
                self.total_time = int(data['totalSecondsTracked'])
            
            # Update completion date if completed
            if self.completion_status in ['completed', 'passed']:
                if not self.last_accessed:
                    self.last_accessed = timezone.now()
            
            # Store detailed progress data
            self.progress_data.update({
                'last_sync': timezone.now().isoformat(),
                'raw_data': data,
                'objectives': data.get('objectives', []),
                'runtime': data.get('runtime', {}),
                'activity_details': data.get('activityDetails', {})
            })
            
            self.save()
            
            # Update associated topic progress with better data passing
            # Find all TopicProgress records linked to this registration
            TopicProgress = apps.get_model('courses', 'TopicProgress')
            
            # First, check for direct references through scorm_registration field
            progress_records = TopicProgress.objects.filter(
                scorm_registration=self.registration_id
            )
            
            for progress in progress_records:
                try:
                    # Pass the full data dictionary to update_scorm_progress
                    # rather than just the registration object
                    progress.update_scorm_progress(data)
                    logger.info(f"Updated TopicProgress {progress.id} from registration {self.registration_id}")
                except Exception as tp_error:
                    logger.error(f"Error updating TopicProgress {progress.id} from registration {self.registration_id}: {str(tp_error)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing completion status: {str(e)}")
            logger.error("Stack trace:", exc_info=True)
            return False

    def get_status_display(self):
        """Get formatted status display with better status mapping"""
        status_map = {
            'not_attempted': 'Not Started',
            'incomplete': 'In Progress',
            'completed': 'Completed',
            'complete': 'Completed',  # Handle both variants
            'passed': 'Passed',
            'failed': 'Failed',
            'unknown': 'Status Unknown'
        }
        
        # Normalize status for display purposes
        normalized_status = self.completion_status.lower() if self.completion_status else 'unknown'
        
        # Handle case variations that might come from SCORM Cloud
        if normalized_status == 'complete':
            normalized_status = 'completed'
        
        # If it's a success/failure, prioritize that over completion status
        success_status = self.success_status.lower() if self.success_status else 'unknown'
        if success_status == 'passed':
            normalized_status = 'passed'
        elif success_status == 'failed':
            normalized_status = 'failed'
            
        return status_map.get(normalized_status, normalized_status.title())

    def get_progress_percentage(self):
        """Calculate progress percentage from stored data"""
        if self.completion_status in ['completed', 'passed']:
            return 100
        elif 'progress' in self.progress_data:
            try:
                return min(float(self.progress_data['progress']), 99)
            except (ValueError, TypeError):
                return 0
        return 0
