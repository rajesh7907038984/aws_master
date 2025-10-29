"""
SCORM Package models for LMS
"""
from django.db import models
from django.core.exceptions import ValidationError
import json
import logging

# Use Django's JSONField if available (Django 3.1+), otherwise use postgres JSONField
try:
    from django.db.models import JSONField
except ImportError:
    try:
        from django.contrib.postgres.fields import JSONField
    except ImportError:
        # Fallback - this shouldn't happen in modern Django
        JSONField = models.TextField  # Will need manual JSON handling

logger = logging.getLogger(__name__)


class ScormPackage(models.Model):
    """Model for storing SCORM package metadata and processing status"""
    
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    
    SCORM_VERSION_CHOICES = [
        ('1.2', 'SCORM 1.2'),
        ('2004', 'SCORM 2004'),
    ]
    
    AUTHORING_TOOL_CHOICES = [
        ('unknown', 'Unknown'),
        ('storyline', 'Articulate Storyline'),
        ('rise', 'Articulate Rise'),
        ('captivate', 'Adobe Captivate'),
        ('ispring', 'iSpring'),
        ('elucidat', 'Elucidat'),
        ('dominknow', 'DominKnow'),
        ('lectora', 'Lectora'),
        ('adapt', 'Adapt Learning'),
        ('other', 'Other'),
    ]
    
    RESOURCE_TYPE_CHOICES = [
        ('webcontent', 'Web Content'),
    ]
    
    RESOURCE_SCORM_TYPE_CHOICES = [
        ('sco', 'SCO'),
        ('asset', 'Asset'),
    ]
    
    title = models.CharField(max_length=255, help_text="Title extracted from manifest")
    version = models.CharField(
        max_length=16, 
        choices=SCORM_VERSION_CHOICES,
        null=True,
        blank=True,
        help_text="SCORM version (1.2 or 2004)"
    )
    authoring_tool = models.CharField(
        max_length=32,
        choices=AUTHORING_TOOL_CHOICES,
        default='unknown',
        null=True,
        blank=True,
        help_text="Authoring tool used to create this SCORM package"
    )
    
    # File storage
    package_zip = models.FileField(
        upload_to='scorm_packages/zips/',
        null=True,
        blank=True,
        help_text="Original uploaded ZIP file"
    )
    extracted_path = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="S3 path to extracted package directory"
    )
    
    # Launch URL - stored for quick access
    launch_url = models.CharField(
        max_length=2048,
        blank=True,
        null=True,
        help_text="Full launch URL path for this SCORM package (e.g., /scorm/player/123/story.html)"
    )
    
    # Manifest data stored as JSON
    manifest_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parsed manifest data (organizations, resources, metadata)"
    )
    
    # Resources data - all manifest resources
    resources = models.JSONField(
        default=list,
        blank=True,
        help_text="Raw manifest resources array"
    )
    
    # Primary resource fields (denormalized for quick access)
    primary_resource_identifier = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="Unique identifier of the primary SCORM resource"
    )
    primary_resource_type = models.CharField(
        max_length=32,
        choices=RESOURCE_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text="SCORM resource @type attribute"
    )
    primary_resource_scorm_type = models.CharField(
        max_length=16,
        choices=RESOURCE_SCORM_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text="adlcp:scormType attribute (sco or asset)"
    )
    primary_resource_href = models.CharField(
        max_length=2048,
        null=True,
        blank=True,
        help_text="Entry point HTML file (href from primary resource)"
    )
    
    # Processing status
    processing_status = models.CharField(
        max_length=32,
        choices=PROCESSING_STATUS_CHOICES,
        default='pending',
        help_text="Package processing status"
    )
    processing_error = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if processing failed"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_scorm_packages',
        help_text="User who uploaded this package"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'scorm'
        ordering = ['-created_at']
        verbose_name = 'SCORM Package'
        verbose_name_plural = 'SCORM Packages'
        indexes = [
            models.Index(fields=['processing_status', 'created_at']),
            models.Index(fields=['created_by', 'processing_status']),
            models.Index(fields=['version', 'authoring_tool']),
        ]
    
    def __str__(self):
        status = self.get_processing_status_display()
        version = self.version or 'Unknown'
        return f"{self.title} ({version}) - {status}"
    
    def get_entry_point(self):
        """
        Extract entry point (launch file) from manifest data
        Follows SCORM 1.2 and 2004 specifications
        Supports common authoring tools: Articulate, Captivate, iSpring, etc.
        
        Uses primary_resource_href if available (stored directly from manifest),
        otherwise falls back to parsing manifest_data.
        
        Returns:
            str: Always returns a valid entry point path (never None or empty)
        """
        try:
            # FIRST: Special handling for Rise packages
            # Rise often exports both SCORM 1.2 and 2004 versions
            # Prefer SCORM 1.2 (scormcontent/index.html) for better compatibility
            # Check for Rise indicators in manifest data (avoid calling detect_authoring_tool to prevent recursion)
            is_rise = False
            if self.manifest_data and isinstance(self.manifest_data, dict):
                manifest_str = json.dumps(self.manifest_data).lower()
                is_rise = 'rise' in manifest_str or 'articulate rise' in manifest_str
            
            if is_rise and self.extracted_path:
                rise_entry_points = [
                    'scormcontent/index.html',  # Rise SCORM 1.2 (preferred)
                    'index.html',                # Rise alternative
                    'lib/index.html',            # Rise variation
                ]
                for entry in rise_entry_points:
                    if self._verify_entry_point_file_exists(entry):
                        logger.info(f"SCORM package {self.id}: Using Rise-specific entry point: {entry}")
                        return entry
            
            # SECOND: Check if we have primary_resource_href stored (most reliable)
            # This is the correct href value from the manifest resource
            if self.primary_resource_href and self.primary_resource_href.strip():
                normalized_href = self._normalize_entry_point(self.primary_resource_href)
                if normalized_href and normalized_href.strip():
                    # Use the stored href directly (it was validated during processing)
                    # We can optionally verify it exists, but for performance, trust it if set
                    logger.debug(f"SCORM package {self.id}: Using primary_resource_href: {normalized_href}")
                    return normalized_href
            
            # THIRD: Check if manifest_data exists and is valid
            if not self.manifest_data or not isinstance(self.manifest_data, dict):
                logger.warning(f"SCORM package {self.id}: No manifest data available")
                return self._get_fallback_entry_point()
            
            # FOURTH: Prefer cached/explicit entry point stored in manifest_data
            # But verify it exists if extracted_path is set (for cache validation)
            cached = self.manifest_data.get('entry_point')
            if isinstance(cached, str) and cached.strip():
                # Ensure normalized before returning
                normalized = self._normalize_entry_point(cached)
                if normalized and normalized.strip():
                    # Verify cached entry point exists (without recursion)
                    # This prevents stale cache issues when files are missing
                    if self.extracted_path and self._verify_entry_point_file_exists(normalized):
                        logger.debug(f"SCORM package {self.id}: Using verified cached entry point: {normalized}")
                        return normalized
                    elif not self.extracted_path:
                        # No extracted_path, can't verify, use cache
                        logger.debug(f"SCORM package {self.id}: Using cached entry point: {normalized}")
                        return normalized
                    else:
                        # Verification failed, clear cache and recompute
                        logger.warning(f"SCORM package {self.id}: Cached entry point invalid ({normalized}), clearing cache...")
                        self.clear_entry_point_cache()
                        # Fall through to recompute
                # If normalization resulted in empty, fall through to recompute
            
            orgs = self.manifest_data.get("organizations", [])
            if not orgs or len(orgs) == 0:
                logger.warning(f"SCORM package {self.id}: No organizations in manifest")
                # Fallback to common entry points
                return self._get_fallback_entry_point()
            
            # Get first organization (default organization)
            first_org = orgs[0]
            
            # Find the first item with an identifierref (recursively)
            def find_first_identifierref(items):
                """Recursively find first item with identifierref"""
                for item in items:
                    identifierref = item.get("identifierref")
                    if identifierref:
                        return identifierref
                    # Check nested items
                    nested_items = item.get("items", [])
                    if nested_items:
                        result = find_first_identifierref(nested_items)
                        if result:
                            return result
                return None
            
            items = first_org.get("items", [])
            if not items:
                logger.warning(f"SCORM package {self.id}: No items in first organization")
                return self._get_fallback_entry_point()
            
            identifierref = find_first_identifierref(items)
            
            if not identifierref:
                logger.warning(f"SCORM package {self.id}: No identifierref found in items")
                return self._get_fallback_entry_point()
            
            # Find resource with this identifierref
            resources = self.manifest_data.get("resources", [])
            if not resources:
                logger.warning(f"SCORM package {self.id}: No resources in manifest")
                return self._get_fallback_entry_point()
            
            # Search for resource matching identifierref
            matching_resource = None
            for resource in resources:
                if resource.get("identifier") == identifierref:
                    matching_resource = resource
                    break
            
            if matching_resource:
                href = matching_resource.get("href", "")
                base = matching_resource.get("base", "")
                
                # Check if resource has scormType="sco" (important for SCORM)
                scorm_type = matching_resource.get("type", "")
                if "sco" in scorm_type.lower() or matching_resource.get("scormType") == "sco":
                    # This is the launchable SCO
                    if href:
                        entry_point = self._normalize_entry_point(href, base)
                        logger.info(f"SCORM package {self.id}: Found entry point '{entry_point}' from SCO resource (href='{href}', base='{base}')")
                        return entry_point
                
                # If no SCO type but has href, still use it
                if href:
                    entry_point = self._normalize_entry_point(href, base)
                    logger.info(f"SCORM package {self.id}: Found entry point '{entry_point}' from resource (href='{href}', base='{base}')")
                    return entry_point
            
            # If no matching resource found, try to find any SCO resource
            logger.warning(f"SCORM package {self.id}: Resource with identifierref '{identifierref}' not found, searching for any SCO resource")
            for resource in resources:
                scorm_type = resource.get("type", "")
                href = resource.get("href", "")
                if href and ("sco" in scorm_type.lower() or resource.get("scormType") == "sco"):
                    base = resource.get("base", "")
                    entry_point = self._normalize_entry_point(href, base)
                    logger.info(f"SCORM package {self.id}: Using first SCO resource as entry point: '{entry_point}'")
                    return entry_point
            
            # Last resort: use first resource with href
            for resource in resources:
                href = resource.get("href", "")
                if href:
                    base = resource.get("base", "")
                    entry_point = self._normalize_entry_point(href, base)
                    logger.info(f"SCORM package {self.id}: Using first resource with href as entry point: '{entry_point}'")
                    return entry_point
            
            logger.warning(f"SCORM package {self.id}: No suitable resource found, using fallback")
            return self._get_fallback_entry_point()
            
        except Exception as e:
            logger.error(f"Error extracting entry point for SCORM package {self.id}: {e}", exc_info=True)
            return self._get_fallback_entry_point()
    
    def _get_fallback_entry_point(self):
        """
        Return common entry points in order of preference
        Verifies file exists if extracted_path is set
        
        Returns:
            str: Always returns a valid entry point (default: "index_lms.html")
        """
        # Common entry points for SCORM 1.2 and 2004, ordered by frequency
        common_entry_points = [
            "index_lms.html",              # Adobe Captivate (most common)
            "index.html",                   # Articulate Rise, iSpring, Adapt, DominKnow, Lectora
            "scormcontent/index.html",     # Articulate Rise (nested structure)
            "story.html",                   # Articulate Storyline
            "story_html5.html",            # Articulate Storyline (HTML5 output)
            "index_lms_html5.html",        # Captivate HTML5
            "launch.html",                  # Elucidat
            "indexAPI.html",                # SCORM 2004 variant
            "scormdriver/indexAPI.html",   # Captivate SCORM 2004
            "scormdriver/indexAPI_lms.html", # Captivate variant
            "a001index.html",               # Lectora specific
            "presentation.html",            # Generic presentation
            "res/index.html",               # Nested structure (various tools)
            "lib/index.html",               # Some Rise variations
        ]
        
        # If we have extracted_path, try to verify which one exists
        if self.extracted_path:
            for entry_point in common_entry_points:
                if self._verify_entry_point_file_exists(entry_point):
                    logger.info(f"SCORM package {self.id}: Found verified fallback: {entry_point}")
                    return entry_point
        
        # If no verification or none found, return most common
        logger.warning(f"SCORM package {self.id}: Using unverified fallback: {common_entry_points[0]}")
        return common_entry_points[0]
    
    def _normalize_entry_point(self, href, base=""):
        """
        Normalize entry point path by combining base and href
        
        Args:
            href: The href from resource (might be relative or absolute)
            base: The base path from resource (optional)
        
        Returns:
            str: Normalized entry point path (always returns non-empty string)
        """
        import os
        from urllib.parse import urlparse
        
        # If href is empty or None, return fallback
        if not href or not isinstance(href, str):
            return self._get_fallback_entry_point()
        
        # If href is an absolute URL, extract the path
        parsed = urlparse(href)
        if parsed.scheme or parsed.netloc:
            # It's a full URL, extract just the path part
            href_path = parsed.path.lstrip('/')
            if href_path:
                # Normalize path separators
                normalized = href_path.replace('\\', '/')
                return normalized if normalized else self._get_fallback_entry_point()
            return self._get_fallback_entry_point()
        
        # Remove leading slashes from href
        href = href.lstrip('/').lstrip('\\')
        if not href:  # Check again after stripping
            return self._get_fallback_entry_point()
        
        # Combine base and href if base is provided
        if base and isinstance(base, str):
            # Remove leading/trailing slashes from base
            base = base.strip('/').strip('\\')
            # Combine with href
            if base:
                combined = f"{base}/{href}".replace('\\', '/')
            else:
                combined = href.replace('\\', '/')
        else:
            combined = href.replace('\\', '/')
        
        # Normalize path (remove double slashes, etc.)
        # Split and rejoin to normalize
        parts = [p for p in combined.split('/') if p]
        normalized = '/'.join(parts)
        
        # If we got an empty string, default to fallback
        if not normalized or not normalized.strip():
            return self._get_fallback_entry_point()
        
        return normalized
    
    def clear_entry_point_cache(self):
        """Clear cached entry point from manifest_data"""
        if self.manifest_data and isinstance(self.manifest_data, dict):
            if 'entry_point' in self.manifest_data:
                del self.manifest_data['entry_point']
                self.save(update_fields=['manifest_data'])
                logger.info(f"SCORM package {self.id}: Cleared cached entry point")
    
    def _verify_entry_point_file_exists(self, entry_point):
        """
        Internal helper to verify entry point file exists in S3
        Handles permission errors gracefully
        
        Args:
            entry_point: Entry point path to verify
            
        Returns:
            bool: True if file exists, False otherwise
        """
        if not self.extracted_path or not entry_point:
            return False
        
        try:
            from django.conf import settings
            import boto3
            from botocore.client import Config
            from botocore.exceptions import ClientError
            
            # Build S3 key - normalize path to remove double slashes
            s3_key = f"{self.extracted_path}/{entry_point}"
            # Remove all double slashes
            while '//' in s3_key:
                s3_key = s3_key.replace('//', '/')
            
            # Get S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
                config=Config(signature_version='s3v4')
            )
            
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            
            # Try head_object first
            try:
                s3_client.head_object(Bucket=bucket_name, Key=s3_key)
                return True
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                
                # If 403 (Forbidden), try list_objects_v2 as fallback
                if error_code == '403':
                    logger.debug(f"HeadObject permission denied, trying list_objects_v2 for {s3_key}")
                    try:
                        response = s3_client.list_objects_v2(
                            Bucket=bucket_name,
                            Prefix=s3_key,
                            MaxKeys=1
                        )
                        return response.get('KeyCount', 0) > 0
                    except Exception as list_error:
                        logger.warning(f"list_objects_v2 also failed: {list_error}")
                        return False
                
                # 404 means definitely doesn't exist
                if error_code == '404':
                    return False
                
                # Other errors
                logger.warning(f"Unexpected error checking S3 key {s3_key}: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying entry point: {e}", exc_info=True)
            return False
    
    def verify_entry_point_exists(self):
        """
        Verify that the entry point file actually exists in S3
        
        Returns:
            tuple: (exists: bool, error_message: str)
        """
        if not self.extracted_path:
            return False, "No extracted path set"
        
        entry_point = self.get_entry_point()
        if not entry_point:
            return False, "No entry point determined"
        
        try:
            from django.conf import settings
            import boto3
            from botocore.client import Config
            from botocore.exceptions import ClientError
            
            # Build S3 key
            s3_key = f"{self.extracted_path}{entry_point}".replace('//', '/')
            
            # Get S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
                config=Config(signature_version='s3v4')
            )
            
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            
            # Check if file exists
            try:
                s3_client.head_object(Bucket=bucket_name, Key=s3_key)
                logger.info(f"SCORM package {self.id}: Entry point verified: {s3_key}")
                return True, None
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == '404':
                    logger.warning(f"SCORM package {self.id}: Entry point not found in S3: {s3_key}. Clearing cache.")
                    # Clear the cached entry point so it will be recomputed
                    self.clear_entry_point_cache()
                    return False, f"Entry point file not found in S3: {s3_key}"
                else:
                    logger.error(f"SCORM package {self.id}: Error checking entry point in S3: {e}")
                    return False, f"Error checking S3: {str(e)}"
        except Exception as e:
            logger.error(f"SCORM package {self.id}: Error verifying entry point: {e}", exc_info=True)
            return False, f"Error verifying entry point: {str(e)}"
    
    def detect_authoring_tool(self) -> str:
        """
        Detect authoring tool from manifest data and entry point patterns
        
        Returns:
            str: Authoring tool identifier
        """
        if not self.manifest_data or not isinstance(self.manifest_data, dict):
            return 'unknown'
        
        entry_point = self.get_entry_point().lower()
        manifest_str = json.dumps(self.manifest_data).lower()
        
        # Check entry point patterns
        if 'story.html' in entry_point or 'story_html5.html' in entry_point:
            # Storyline uses story.html or story_html5.html
            return 'storyline'
        elif 'scormcontent/index.html' in entry_point or 'lib/index.html' in entry_point:
            # Rise typically has scormcontent/ or lib/ structure
            return 'rise'
        elif 'rise' in entry_point or 'rise' in manifest_str or 'articulate rise' in manifest_str:
            # Explicit Rise mentions
            return 'rise'
        elif 'index_lms.html' in entry_point or 'index_lms_html5.html' in entry_point:
            # Could be Captivate or Storyline - check manifest metadata
            if 'captivate' in manifest_str:
                return 'captivate'
            elif 'articulate' in manifest_str or 'storyline' in manifest_str:
                return 'storyline'
            return 'captivate'  # Default assumption for index_lms.html
        elif 'index.html' in entry_point:
            # Could be multiple tools
            if 'ispring' in manifest_str:
                return 'ispring'
            elif 'adapt' in manifest_str:
                return 'adapt'
            elif 'lectora' in manifest_str or 'a001index.html' in entry_point:
                return 'lectora'
            elif 'dominknow' in manifest_str:
                return 'dominknow'
        elif 'launch.html' in entry_point:
            return 'elucidat'
        
        # Check manifest metadata for authoring tool hints
        metadata = self.manifest_data.get('metadata', {})
        metadata_str = json.dumps(metadata).lower()
        
        if 'articulate' in metadata_str:
            if 'rise' in metadata_str:
                return 'rise'
            elif 'storyline' in metadata_str:
                return 'storyline'
            return 'storyline'  # Default for Articulate
        elif 'captivate' in metadata_str:
            return 'captivate'
        elif 'ispring' in metadata_str:
            return 'ispring'
        elif 'elucidat' in metadata_str:
            return 'elucidat'
        elif 'dominknow' in metadata_str or 'dominknow' in manifest_str:
            return 'dominknow'
        elif 'lectora' in metadata_str or 'lectora' in manifest_str:
            return 'lectora'
        elif 'adapt' in metadata_str or 'adapt' in manifest_str:
            return 'adapt'
        
        return 'unknown'
    
    def get_launch_url(self, request=None):
        """
        Get the full launch URL for this SCORM package
        
        Args:
            request: Optional HttpRequest object to build absolute URL
        
        Returns:
            str: Launch URL path or full URL if request provided
        """
        if self.launch_url:
            # Use cached launch URL
            if request:
                # Return absolute URL
                return request.build_absolute_uri(self.launch_url)
            return self.launch_url
        
        # Generate launch URL dynamically using primary_resource_href
        entry_point = self.primary_resource_href
        if not entry_point or not entry_point.strip():
            return None
        
        try:
            from django.urls import reverse
            launch_path = reverse('scorm:player', args=[self.id, entry_point])
            
            if request:
                return request.build_absolute_uri(launch_path)
            return launch_path
        except Exception as e:
            logger.error(f"Error generating launch URL for package {self.id}: {e}")
            # Fallback to manual construction
            launch_path = f"/scorm/player/{self.id}/{entry_point}"
            if request:
                return request.build_absolute_uri(launch_path)
            return launch_path
    
    def update_launch_url(self):
        """
        Update the cached launch_url field based on primary_resource_href
        Should be called after entry point is determined during processing
        """
        entry_point = self.primary_resource_href
        if entry_point and entry_point.strip():
            try:
                from django.urls import reverse
                self.launch_url = reverse('scorm:player', args=[self.id, entry_point])
            except Exception as e:
                logger.warning(f"Could not generate launch URL for package {self.id}: {e}")
                # Fallback
                self.launch_url = f"/scorm/player/{self.id}/{entry_point}"
        else:
            self.launch_url = None
    
    def save(self, *args, **kwargs):
        """
        Override save to handle cache invalidation on re-upload
        """
        # If package_zip changed (re-upload), clear cached entry point
        if self.pk:
            try:
                old_instance = ScormPackage.objects.get(pk=self.pk)
                if old_instance.package_zip != self.package_zip:
                    logger.info(f"Package {self.pk} re-uploaded, clearing entry point cache")
                    self.clear_entry_point_cache()
            except ScormPackage.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up S3 files when SCORM package is deleted
        """
        logger.info(f"Deleting SCORM package {self.id}: {self.title}")
        
        try:
            # 1. Delete extracted files from S3
            if self.extracted_path:
                try:
                    from django.conf import settings
                    import boto3
                    from botocore.client import Config
                    
                    s3_client = boto3.client(
                        's3',
                        aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                        aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
                        config=Config(signature_version='s3v4')
                    )
                    
                    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                    
                    # List and delete all files in extracted path
                    logger.info(f"Deleting S3 files at: {self.extracted_path}")
                    paginator = s3_client.get_paginator('list_objects_v2')
                    pages = paginator.paginate(Bucket=bucket_name, Prefix=self.extracted_path)
                    
                    delete_count = 0
                    for page in pages:
                        if 'Contents' in page:
                            for obj in page['Contents']:
                                try:
                                    s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                                    delete_count += 1
                                except Exception as e:
                                    logger.warning(f"Error deleting S3 object {obj['Key']}: {e}")
                    
                    logger.info(f"Deleted {delete_count} files from S3")
                except Exception as e:
                    logger.error(f"Error cleaning up S3 files for package {self.id}: {e}", exc_info=True)
            
            # 2. Delete ZIP file from S3
            if self.package_zip:
                try:
                    self.package_zip.delete(save=False)
                    logger.info(f"Deleted package ZIP file: {self.package_zip.name}")
                except Exception as e:
                    logger.error(f"Error deleting package ZIP: {e}")
            
        except Exception as e:
            logger.error(f"Error during SCORM package cleanup: {e}", exc_info=True)
        
        # Call parent delete
        super().delete(*args, **kwargs)
        logger.info(f"Successfully deleted SCORM package {self.id}")
    
    def validate_package(self):
        """Validate that package has required manifest structure"""
        if not self.manifest_data:
            raise ValidationError("Manifest data is required")
        
        if not self.version:
            raise ValidationError("SCORM version must be set")
        
        # Check for basic manifest structure
        if "organizations" not in self.manifest_data:
            raise ValidationError("Manifest must contain organizations")
        
        if "resources" not in self.manifest_data:
            raise ValidationError("Manifest must contain resources")
    
    def clean(self):
        """Run validation on save"""
        super().clean()
        
        # Auto-detect authoring tool if not set
        if not self.authoring_tool or self.authoring_tool == 'unknown':
            detected = self.detect_authoring_tool()
            if detected != 'unknown':
                self.authoring_tool = detected
        
        # Auto-update launch URL if entry point exists but launch_url doesn't
        if self.processing_status == 'ready' and not self.launch_url:
            self.update_launch_url()
        
        if self.processing_status == 'ready':
            try:
                self.validate_package()
            except ValidationError as e:
                logger.warning(f"Package {self.id} validation failed: {e}")
                # Don't raise - allow saving but log warning

