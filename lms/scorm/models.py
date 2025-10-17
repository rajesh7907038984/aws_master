import os
import zipfile
import json
import logging
from django.db import models
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from django.core.exceptions import ValidationError
from courses.models import Topic, Course
from users.models import CustomUser
import uuid
import xml.etree.ElementTree as ET
from .storage import SCORMS3Storage

logger = logging.getLogger(__name__)

def elearning_package_path(instance, filename):
    """Generate file path for e-learning packages (SCORM, xAPI, cmi5)"""
    # Get the base filename and extension
    name, ext = os.path.splitext(filename)
    
    # Generate a unique identifier
    unique_id = uuid.uuid4().hex[:8]
    
    # Clean the filename
    name = "".join(c for c in name if c.isalnum() or c in ['-', '_']).strip()
    if len(name) > 50:
        name = name[:50]
    
    # Construct the new filename
    new_filename = "{}_{}{}".format(name, unique_id, ext.lower())
    
    return "elearning/packages/{}".format(new_filename)

class ELearningPackage(models.Model):
    """Model for e-learning packages (SCORM, xAPI, cmi5)"""
    
    PACKAGE_TYPES = [
        ('SCORM_1_2', 'SCORM 1.2'),
        ('SCORM_2004', 'SCORM 2004'),
        ('XAPI', 'xAPI (Tin Can)'),
        ('CMI5', 'cmi5'),
        ('AICC', 'AICC'),
    ]
    
    topic = models.OneToOneField(
        Topic,
        on_delete=models.CASCADE,
        related_name='elearning_package',
        help_text="The topic this e-learning package belongs to"
    )
    
    package_file = models.FileField(
        upload_to=elearning_package_path,
        storage=SCORMS3Storage(),
        help_text="The e-learning package ZIP file"
    )
    
    package_type = models.CharField(
        max_length=20,
        choices=PACKAGE_TYPES,
        help_text="The type of e-learning package"
    )
    
    # Package metadata
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50, blank=True)
    organization = models.CharField(max_length=255, blank=True)
    
    # Package structure
    manifest_path = models.CharField(max_length=500, blank=True)
    launch_file = models.CharField(max_length=500, blank=True)
    extracted_path = models.CharField(max_length=500, blank=True)
    
    # xAPI specific fields
    xapi_endpoint = models.URLField(blank=True, help_text="xAPI endpoint URL")
    xapi_actor = models.JSONField(default=dict, blank=True, help_text="xAPI actor information")
    
    # cmi5 specific fields
    cmi5_au_id = models.CharField(max_length=255, blank=True, help_text="cmi5 AU ID")
    cmi5_launch_url = models.URLField(blank=True, help_text="cmi5 launch URL")
    
    # Status
    is_extracted = models.BooleanField(default=False)
    extraction_error = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return "{} Package: {}".format(self.get_package_type_display(), self.title or self.topic.title)
    
    def extract_package(self):
        """Extract e-learning package to local media directory"""
        try:
            if not self.package_file:
                raise ValidationError("No package file to extract")
            
            # Auto-detect package type if not set
            if not self.package_type:
                detected_type = self.detect_package_type()
                if detected_type:
                    self.package_type = detected_type
                    self.save()
                else:
                    # Default to SCORM_1_2 if detection fails
                    self.package_type = 'SCORM_1_2'
                    self.save()
            
            # Create topic-based directory structure using the custom storage
            topic_dir = "packages/{}".format(self.topic.id)
            
            # Ensure the directory exists using the storage system
            if not self.package_file.storage.exists(topic_dir):
                # Create directory by creating a temporary file and then removing it
                temp_file = os.path.join(topic_dir, '.temp')
                from django.core.files.base import ContentFile
                self.package_file.storage.save(temp_file, ContentFile(b''))
                self.package_file.storage.delete(temp_file)
            
            # Get the full path for extraction
            full_topic_dir = self.package_file.storage.path(topic_dir)
            
            # Extract the ZIP file
            # Handle case where file might be in S3 but we need local access
            if hasattr(self.package_file.storage, 'path'):
                # S3 storage - use path directly
                zip_path = self.package_file.path
            else:
                # Remote storage (S3) - download to temp file first
                import tempfile
                import io
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                    # Download from S3 to temp file
                    # Handle both file-like objects and bytes properly
                    try:
                        # Try to open as file-like object first
                        with self.package_file.open('rb') as source:
                            content = source.read()
                            temp_file.write(content)
                    except (AttributeError, TypeError) as e:
                        # If that fails, handle different cases
                        if hasattr(self.package_file, 'read'):
                            # It's a file-like object
                            content = self.package_file.read()
                            temp_file.write(content)
                        elif isinstance(self.package_file, bytes):
                            # It's already bytes
                            temp_file.write(self.package_file)
                        else:
                            # Try to get the file content another way
                            try:
                                # For Django FileField, try to get the file content
                                if hasattr(self.package_file, 'file'):
                                    content = self.package_file.file.read()
                                    temp_file.write(content)
                                else:
                                    # Last resort: try to read as bytes
                                    content = bytes(self.package_file)
                                    temp_file.write(content)
                            except Exception as inner_e:
                                logger.error("Error reading package file: {}".format(str(inner_e)))
                                raise ValidationError("Could not read package file: {}".format(str(inner_e)))
                    zip_path = temp_file.name
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(full_topic_dir)
            
            # Clean up temp file if we created one
            if not hasattr(self.package_file.storage, 'path'):
                os.unlink(zip_path)
            
            # Find and parse the manifest based on package type
            manifest_path = self._find_manifest(full_topic_dir)
            if manifest_path:
                # Store relative path for storage compatibility
                self.manifest_path = os.path.relpath(manifest_path, full_topic_dir)
                self._parse_manifest(manifest_path)
            
            # Find the launch file
            self.launch_file = self._find_launch_file(full_topic_dir)
            if self.launch_file:
                logger.info(f"SCORM: Launch file detected: {self.launch_file} for package type {self.package_type}")
            else:
                logger.warning(f"SCORM: No launch file found for package type {self.package_type}")
            self.extracted_path = topic_dir  # Store relative path
            self.is_extracted = True
            self.extraction_error = ""
            self.save()
            
            logger.info("Successfully extracted {} package for topic {}".format(self.package_type, self.topic.id))
            return True
            
        except Exception as e:
            error_msg = "Error extracting {} package: {}".format(getattr(self, 'package_type', 'unknown'), str(e))
            logger.error(error_msg)
            self.extraction_error = error_msg
            self.save()
            return False
    
    def _find_manifest(self, base_path):
        """Find the e-learning manifest file based on package type"""
        manifest_files = []
        
        if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
            manifest_files = ['imsmanifest.xml', 'manifest.xml']
        elif self.package_type == 'XAPI':
            manifest_files = ['tincan.xml', 'tincan.json']
        elif self.package_type == 'CMI5':
            manifest_files = ['cmi5.xml', 'cmi5.json']
        elif self.package_type == 'AICC':
            manifest_files = ['coursestruct.cst', 'au.txt']
        
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower() in [f.lower() for f in manifest_files]:
                    return os.path.join(root, file)
        return None
    
    def _parse_manifest(self, manifest_path):
        """Parse e-learning manifest to extract metadata based on package type"""
        try:
            if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
                self._parse_scorm_manifest(manifest_path)
            elif self.package_type == 'XAPI':
                self._parse_xapi_manifest(manifest_path)
            elif self.package_type == 'CMI5':
                self._parse_cmi5_manifest(manifest_path)
            elif self.package_type == 'AICC':
                self._parse_aicc_manifest(manifest_path)
            
            self.save()
            
        except Exception as e:
            logger.error("Error parsing {} manifest: {}".format(self.package_type, str(e)))
    
    def _parse_scorm_manifest(self, manifest_path):
        """Parse SCORM manifest to extract metadata"""
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        
        # Extract title
        title_elem = root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p0}title')
        if title_elem is not None:
            self.title = title_elem.text or ""
        
        # Extract description
        desc_elem = root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p0}description')
        if desc_elem is not None:
            self.description = desc_elem.text or ""
        
        # Extract version
        version_elem = root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p0}version')
        if version_elem is not None:
            self.version = version_elem.text or ""
        
        # Extract organization
        org_elem = root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p0}organization')
        if org_elem is not None:
            self.organization = org_elem.get('identifier', '')
    
    def _parse_xapi_manifest(self, manifest_path):
        """Parse xAPI (Tin Can) manifest to extract metadata"""
        if manifest_path.endswith('.json'):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.title = data.get('name', {}).get('en-US', '') or data.get('name', '')
            self.description = data.get('description', {}).get('en-US', '') or data.get('description', '')
            self.version = data.get('version', '')
            
            # Extract xAPI specific data
            if 'launch' in data:
                self.xapi_endpoint = data['launch']
            if 'actor' in data:
                self.xapi_actor = data['actor']
        else:
            # Parse XML format
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            
            # Basic parsing for XML xAPI manifests
            title_elem = root.find('.//title')
            if title_elem is not None:
                self.title = title_elem.text or ""
    
    def _parse_cmi5_manifest(self, manifest_path):
        """Parse cmi5 manifest to extract metadata"""
        if manifest_path.endswith('.json'):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.title = data.get('name', {}).get('en-US', '') or data.get('name', '')
            self.description = data.get('description', {}).get('en-US', '') or data.get('description', '')
            
            # Extract cmi5 specific data
            if 'id' in data:
                self.cmi5_au_id = data['id']
            if 'launch' in data:
                self.cmi5_launch_url = data['launch']
        else:
            # Parse XML format
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            
            # Basic parsing for XML cmi5 manifests
            title_elem = root.find('.//title')
            if title_elem is not None:
                self.title = title_elem.text or ""
    
    def _parse_aicc_manifest(self, manifest_path):
        """Parse AICC manifest to extract metadata"""
        # AICC uses different file formats
        if manifest_path.endswith('.cst'):
            # Parse course structure file
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Basic parsing for AICC course structure
                lines = content.split('\n')
                for line in lines:
                    if line.startswith('COURSE_TITLE'):
                        self.title = line.split('=')[1].strip() if '=' in line else ""
        elif manifest_path.endswith('.txt'):
            # Parse AU file
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Basic parsing for AICC AU file
                lines = content.split('\n')
                for line in lines:
                    if line.startswith('TITLE'):
                        self.title = line.split('=')[1].strip() if '=' in line else ""
    
    def _find_launch_file(self, base_path):
        """Find the main launch file based on package type with intelligent priority selection"""
        launch_files = []
        
        if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
            launch_files = [
                # Articulate Storyline files (priority order)
                'index_lms.html',      # LMS mode (SCORM integration) - HIGHEST PRIORITY
                'story.html',          # Standalone mode (no SCORM)
                'analytics-frame.html', # Analytics mode
                'lms/goodbye.html',    # Exit page (SCORM completion)
                
                # Standard SCORM files
                'index.html', 
                'launch.html', 
                'start.html', 
                'main.html',
                
                # SCORM content subdirectory patterns
                'scormcontent/index.html',
                'scormcontent/launch.html',
                'scormcontent/start.html',
                'content/index.html',
                'data/index.html',
                
                # Additional Articulate files
                'lms/blank.html',      # Blank page
                'lms/AICCComm.html'   # AICC communication
            ]
        elif self.package_type == 'XAPI':
            launch_files = [
                # xAPI specific files (priority order)
                'tincan.html',          # xAPI Tin Can launch file
                'launch.html',          # xAPI launch file
                'player.html',          # xAPI player
                'index.html',           # Standard HTML entry point
                'start.html',           # Alternative start file
                'main.html',            # Main content file
                
                # xAPI subdirectory patterns
                'tincan/index.html',
                'tincan/launch.html',
                'xapi/index.html',
                'xapi/launch.html',
                'content/index.html',
                'data/index.html',
                'player/index.html'
            ]
        elif self.package_type == 'CMI5':
            launch_files = [
                # cmi5 specific files (priority order)
                'cmi5.html',            # cmi5 launch file
                'au.html',              # Assignable Unit launch
                'launch.html',          # cmi5 launch file
                'player.html',          # cmi5 player
                'index.html',           # Standard HTML entry point
                'start.html',           # Alternative start file
                'main.html',            # Main content file
                
                # cmi5 subdirectory patterns
                'cmi5/index.html',
                'cmi5/launch.html',
                'au/index.html',
                'au/launch.html',
                'content/index.html',
                'data/index.html',
                'player/index.html'
            ]
        elif self.package_type == 'AICC':
            launch_files = [
                # AICC specific files (priority order)
                'au.html',              # AICC Assignable Unit
                'launch.html',          # AICC launch file
                'player.html',          # AICC player
                'index.html',           # Standard HTML entry point
                'start.html',           # Alternative start file
                'main.html',            # Main content file
                
                # AICC subdirectory patterns
                'aicc/index.html',
                'aicc/launch.html',
                'au/index.html',
                'au/launch.html',
                'content/index.html',
                'data/index.html',
                'player/index.html'
            ]
        
        # Intelligent priority-based search
        found_files = []
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower() in [f.lower() for f in launch_files]:
                    file_path = os.path.relpath(os.path.join(root, file), base_path)
                    found_files.append(file_path)
        
        # Return the highest priority file found
        if found_files:
            # Sort by priority (order in launch_files list)
            for preferred_file in launch_files:
                for found_file in found_files:
                    if found_file.lower() == preferred_file.lower():
                        logger.info(f"SCORM: Selected launch file '{found_file}' (priority: {preferred_file}) for package type {self.package_type}")
                        return found_file
            
            # Fallback to first found file
            logger.info(f"SCORM: Using fallback launch file '{found_files[0]}' for package type {self.package_type}")
            return found_files[0]
        
        # If no common launch file found, look for HTML files
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith('.html'):
                    file_path = os.path.relpath(os.path.join(root, file), base_path)
                    logger.info(f"SCORM: Using generic HTML file '{file_path}' for package type {self.package_type}")
                    return file_path
        
        logger.warning(f"SCORM: No launch file found for package type {self.package_type}")
        return None
    
    def detect_package_type(self):
        """Detect the package type based on manifest files"""
        if not self.package_file:
            return None
        
        try:
            # Handle both S3 and remote storage
            if hasattr(self.package_file.storage, 'path'):
                # S3 storage - use path directly
                zip_path = self.package_file.path
            else:
                # Remote storage - need to handle differently
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                    try:
                        with self.package_file.open('rb') as source:
                            content = source.read()
                            temp_file.write(content)
                    except (AttributeError, TypeError):
                        # Handle bytes or other formats
                        if hasattr(self.package_file, 'read'):
                            content = self.package_file.read()
                            temp_file.write(content)
                        elif isinstance(self.package_file, bytes):
                            temp_file.write(self.package_file)
                        else:
                            return None
                    zip_path = temp_file.name
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                
                # Check for SCORM manifests
                if any('imsmanifest.xml' in f.lower() for f in file_list):
                    # Check SCORM version by examining the manifest content
                    try:
                        manifest_content = zip_ref.read('imsmanifest.xml').decode('utf-8')
                        if 'scorm_2004' in manifest_content.lower() or 'adlcp:scormtype' in manifest_content.lower():
                            return 'SCORM_2004'
                        else:
                            return 'SCORM_1_2'
                    except:
                        # Default to SCORM 1.2 if we can't determine version
                        return 'SCORM_1_2'
                
                # Check for xAPI manifests
                elif any('tincan.xml' in f.lower() or 'tincan.json' in f.lower() for f in file_list):
                    return 'XAPI'
                
                # Check for cmi5 manifests
                elif any('cmi5.xml' in f.lower() or 'cmi5.json' in f.lower() for f in file_list):
                    return 'CMI5'
                
                # Check for AICC manifests
                elif any('coursestruct.cst' in f.lower() or 'au.txt' in f.lower() for f in file_list):
                    return 'AICC'
            
            # Clean up temp file if we created one
            if not hasattr(self.package_file.storage, 'path'):
                os.unlink(zip_path)
                
        except Exception as e:
            logger.error("Error detecting package type: {}".format(str(e)))
        
        return None
    
    def get_launch_url(self):
        """Get the URL to launch this e-learning package"""
        if not self.is_extracted or not self.launch_file:
            return None
        
        return "/scorm/launch/{}/".format(self.topic.id)
    
    def get_content_url(self):
        """Get the URL to access the e-learning content"""
        if not self.is_extracted or not self.launch_file:
            return None
        
        return "/scorm/content/{}/{}".format(self.topic.id, self.launch_file)

# Backward compatibility alias
SCORMPackage = ELearningPackage

class ELearningTracking(models.Model):
    """Model for tracking e-learning learner interactions (SCORM, xAPI, cmi5)"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='elearning_tracking'
    )
    
    elearning_package = models.ForeignKey(
        ELearningPackage,
        on_delete=models.CASCADE,
        related_name='tracking_records'
    )
    
    # Registration ID for SCORM 2004 and cmi5
    registration_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # SCORM 1.2 and 2004 data model elements
    completion_status = models.CharField(
        max_length=20,
        choices=[
            ('completed', 'Completed'),
            ('incomplete', 'Incomplete'),
            ('not attempted', 'Not Attempted'),
            ('unknown', 'Unknown')
        ],
        default='not attempted'
    )
    
    success_status = models.CharField(
        max_length=20,
        choices=[
            ('passed', 'Passed'),
            ('failed', 'Failed'),
            ('unknown', 'Unknown')
        ],
        default='unknown'
    )
    
    # Score tracking
    score_raw = models.FloatField(null=True, blank=True)
    score_min = models.FloatField(null=True, blank=True)
    score_max = models.FloatField(null=True, blank=True)
    score_scaled = models.FloatField(null=True, blank=True)
    
    # Progress tracking
    progress_measure = models.FloatField(null=True, blank=True)
    completion_threshold = models.FloatField(null=True, blank=True)
    
    # Time tracking
    total_time = models.DurationField(null=True, blank=True)
    session_time = models.DurationField(null=True, blank=True)
    
    # Location and suspend data
    location = models.CharField(max_length=500, blank=True)
    suspend_data = models.TextField(blank=True)
    launch_data = models.TextField(blank=True)
    
    # Entry and exit
    entry = models.CharField(max_length=20, choices=[
        ('ab-initio', 'Ab Initio'),
        ('resume', 'Resume')
    ], default='ab-initio')
    
    exit_value = models.CharField(max_length=20, choices=[
        ('time-out', 'Time Out'),
        ('suspend', 'Suspend'),
        ('logout', 'Logout'),
        ('normal', 'Normal'),
        ('ab-initio', 'Ab Initio')
    ], blank=True)
    
    # SCORM 2004 specific fields
    credit = models.CharField(max_length=20, choices=[
        ('credit', 'Credit'),
        ('no-credit', 'No Credit')
    ], default='credit')
    
    mode = models.CharField(max_length=20, choices=[
        ('browse', 'Browse'),
        ('normal', 'Normal'),
        ('review', 'Review')
    ], default='normal')
    
    # Learner preferences
    learner_preference_audio_level = models.FloatField(null=True, blank=True)
    learner_preference_language = models.CharField(max_length=10, blank=True)
    learner_preference_delivery_speed = models.FloatField(null=True, blank=True)
    learner_preference_audio_captioning = models.BooleanField(null=True, blank=True)
    
    # Student data
    student_data_mastery_score = models.FloatField(null=True, blank=True)
    student_data_max_time_allowed = models.DurationField(null=True, blank=True)
    student_data_time_limit_action = models.CharField(max_length=50, blank=True)
    
    # Objectives tracking
    objectives = models.JSONField(default=dict, help_text="SCORM objectives data")
    
    # Interactions tracking
    interactions = models.JSONField(default=dict, help_text="SCORM interactions data")
    
    # Comments
    comments_from_learner = models.JSONField(default=list, help_text="Comments from learner")
    comments_from_lms = models.JSONField(default=list, help_text="Comments from LMS")
    
    # Additional data
    raw_data = models.JSONField(
        default=dict,
        help_text="Raw SCORM data from the package"
    )
    
    # Attempt tracking
    attempt_count = models.PositiveIntegerField(default=0, help_text="Number of attempts made on this SCORM package")
    
    # Timestamps
    first_launch = models.DateTimeField(null=True, blank=True)
    last_launch = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'elearning_package']
        ordering = ['-updated_at']
    
    def __str__(self):
        return "{} - {}".format(self.user.username, self.elearning_package.title)
    
    def update_progress(self, scorm_data):
        """Update progress based on SCORM data"""
        self.raw_data.update(scorm_data)
        
        # Update completion status
        if 'cmi.completion_status' in scorm_data:
            self.completion_status = scorm_data['cmi.completion_status']
        
        # Update success status
        if 'cmi.success_status' in scorm_data:
            self.success_status = scorm_data['cmi.success_status']
        
        # Enhanced score processing - handle both SCORM 1.2 and 2004 elements
        score_updated = False
        
        # SCORM 1.2 score elements
        if 'cmi.core.score.raw' in scorm_data:
            try:
                self.score_raw = float(scorm_data['cmi.core.score.raw']) if scorm_data['cmi.core.score.raw'] else None
                score_updated = True
            except (ValueError, TypeError):
                pass
        
        if 'cmi.core.score.min' in scorm_data:
            try:
                self.score_min = float(scorm_data['cmi.core.score.min']) if scorm_data['cmi.core.score.min'] else None
            except (ValueError, TypeError):
                pass
        
        if 'cmi.core.score.max' in scorm_data:
            try:
                self.score_max = float(scorm_data['cmi.core.score.max']) if scorm_data['cmi.core.score.max'] else None
            except (ValueError, TypeError):
                pass
        
        # SCORM 2004 score elements
        if 'cmi.score.raw' in scorm_data:
            try:
                self.score_raw = float(scorm_data['cmi.score.raw']) if scorm_data['cmi.score.raw'] else None
                score_updated = True
            except (ValueError, TypeError):
                pass
        
        if 'cmi.score.min' in scorm_data:
            try:
                self.score_min = float(scorm_data['cmi.score.min']) if scorm_data['cmi.score.min'] else None
            except (ValueError, TypeError):
                pass
        
        if 'cmi.score.max' in scorm_data:
            try:
                self.score_max = float(scorm_data['cmi.score.max']) if scorm_data['cmi.score.max'] else None
            except (ValueError, TypeError):
                pass
        
        if 'cmi.score.scaled' in scorm_data:
            try:
                self.score_scaled = float(scorm_data['cmi.score.scaled']) if scorm_data['cmi.score.scaled'] else None
                score_updated = True
            except (ValueError, TypeError):
                pass
        
        # Set default max score if we have raw score but no max
        if self.score_raw is not None and self.score_max is None:
            if 0 <= self.score_raw <= 1:
                self.score_max = 1.0
            elif 0 <= self.score_raw <= 100:
                self.score_max = 100
            else:
                self.score_max = 100  # Default fallback
        
        # Update progress measure
        if 'cmi.progress_measure' in scorm_data:
            self.progress_measure = float(scorm_data['cmi.progress_measure']) if scorm_data['cmi.progress_measure'] else None
        
        # Update time tracking
        if 'cmi.total_time' in scorm_data:
            # Parse SCORM time format (PT1H30M15S)
            self.total_time = self._parse_scorm_time(scorm_data['cmi.total_time'])
        
        if 'cmi.session_time' in scorm_data:
            self.session_time = self._parse_scorm_time(scorm_data['cmi.session_time'])
        
        # Update timestamps
        now = timezone.now()
        if not self.first_launch:
            self.first_launch = now
        self.last_launch = now
        
        if self.completion_status == 'completed':
            self.completion_date = now
        
        self.save()
    
    def _parse_scorm_time(self, time_str):
        """ENHANCED: Parse SCORM time format (PT1H30M15.5S) to timedelta with comprehensive format support"""
        if not time_str or time_str == 'PT0S' or time_str.strip() == '':
            return None
        
        try:
            # Clean the time string
            time_str = time_str.strip()
            original_time_str = time_str
            
            # Handle different time formats
            if time_str.startswith('PT'):
                # Standard SCORM format: PT1H30M15.5S
                time_str = time_str[2:]  # Remove PT prefix
            elif ':' in time_str:
                # Handle HH:MM:SS format
                return self._parse_colon_time(time_str)
            elif time_str.isdigit():
                # Handle seconds only
                return timedelta(seconds=float(time_str))
            elif time_str.replace('.', '').isdigit():
                # Handle decimal seconds
                return timedelta(seconds=float(time_str))
            
            hours = 0
            minutes = 0
            seconds = 0
            
            # ENHANCED: Parse hours with better error handling
            if 'H' in time_str:
                try:
                    h_part = time_str.split('H')[0]
                    if h_part:  # Only parse if there's content before H
                        hours = float(h_part)
                    time_str = time_str.split('H')[1] if 'H' in time_str else time_str
                except (ValueError, IndexError):
                    logger.warning(f"SCORM: Error parsing hours from: {original_time_str}")
            
            # ENHANCED: Parse minutes with better error handling
            if 'M' in time_str:
                try:
                    m_part = time_str.split('M')[0]
                    if m_part:  # Only parse if there's content before M
                        minutes = float(m_part)
                    time_str = time_str.split('M')[1] if 'M' in time_str else time_str
                except (ValueError, IndexError):
                    logger.warning(f"SCORM: Error parsing minutes from: {original_time_str}")
            
            # ENHANCED: Parse seconds with better error handling
            if 'S' in time_str:
                try:
                    s_part = time_str.split('S')[0]
                    if s_part:  # Only parse if there's content before S
                        seconds = float(s_part)
                except (ValueError, IndexError):
                    logger.warning(f"SCORM: Error parsing seconds from: {original_time_str}")
            
            from datetime import timedelta
            result = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            
            # ENHANCED: Log successful parsing with more details
            logger.info(f"SCORM: Successfully parsed time '{original_time_str}' -> hours:{hours}, minutes:{minutes}, seconds:{seconds} -> {result}")
            return result
            
        except Exception as e:
            logger.error("SCORM: Error parsing time '{}': {}".format(original_time_str if 'original_time_str' in locals() else time_str, str(e)))
            return None
    
    def _parse_colon_time(self, time_str):
        """ENHANCED: Parse HH:MM:SS format to timedelta with better error handling"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                result = timedelta(hours=hours, minutes=minutes, seconds=seconds)
                logger.info(f"SCORM: Parsed colon time '{time_str}' -> {result}")
                return result
            elif len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])
                result = timedelta(minutes=minutes, seconds=seconds)
                logger.info(f"SCORM: Parsed colon time '{time_str}' -> {result}")
                return result
            else:
                seconds = float(parts[0])
                result = timedelta(seconds=seconds)
                logger.info(f"SCORM: Parsed colon time '{time_str}' -> {result}")
                return result
        except (ValueError, TypeError) as e:
            logger.error("SCORM: Error parsing colon time '{}': {}".format(time_str, str(e)))
            return None
        except Exception as e:
            logger.error("SCORM: Unexpected error parsing colon time '{}': {}".format(time_str, str(e)))
            return None
    
    def format_scorm_time(self, timedelta_obj):
        """Convert timedelta to SCORM PT format"""
        if not timedelta_obj:
            return 'PT0S'
        
        total_seconds = timedelta_obj.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        
        # Handle decimal seconds properly
        if seconds == int(seconds):
            seconds = int(seconds)
        
        if hours > 0:
            return f"PT{hours}H{minutes}M{seconds}S"
        elif minutes > 0:
            return f"PT{minutes}M{seconds}S"
        else:
            return f"PT{seconds}S"
    
    def get_progress_percentage(self):
        """Get progress as percentage with enhanced logic"""
        # First check progress_measure
        if self.progress_measure is not None:
            return min(100, max(0, self.progress_measure * 100))
        
        # Check completion status
        if self.completion_status == 'completed':
            return 100
        
        # Check if we have time spent (indicates some progress)
        if self.total_time and self.total_time.total_seconds() > 0:
            # If user spent time, assume at least some progress
            return 25  # Minimum progress for time spent
        
        # Check if we have scores (indicates interaction)
        if self.score_raw is not None:
            return 50  # Progress for score interaction
        
        # Check if we have location or suspend data (indicates bookmarking)
        if self.location or self.suspend_data:
            return 75  # Progress for bookmarking
        
        return 0
    
    def is_completed(self):
        """Check if the SCORM package is completed"""
        return self.completion_status == 'completed'
    
    def is_passed(self):
        """Check if the SCORM package is passed"""
        return self.success_status == 'passed'
    
    def validate_score(self):
        """Validate that score_raw is within the valid range"""
        if self.score_raw is not None and self.score_min is not None and self.score_max is not None:
            if not (self.score_min <= self.score_raw <= self.score_max):
                logger.warning(f"SCORM Score Validation: Score {self.score_raw} is outside valid range [{self.score_min}, {self.score_max}] for user {self.user.id}")
                return False
        return True
    
    def get_score_percentage(self):
        """Enhanced score percentage calculation with comprehensive fallbacks"""
        logger.info(f"SCORM: Calculating score percentage for user {self.user.id}")
        logger.info(f"SCORM: Score data - raw: {self.score_raw}, min: {self.score_min}, max: {self.score_max}, scaled: {self.score_scaled}")
        
        # Method 1: Use raw and max scores if both available
        if self.score_raw is not None and self.score_max is not None and self.score_max > 0:
            percentage = (self.score_raw / self.score_max) * 100
            result = min(100, max(0, percentage))
            logger.info(f"SCORM: Calculated percentage from raw/max: {result}%")
            return result
        
        # Method 2: Use scaled score if available (0-1 range)
        if self.score_scaled is not None:
            result = min(100, max(0, self.score_scaled * 100))
            logger.info(f"SCORM: Calculated percentage from scaled: {result}%")
            return result
        
        # Method 3: Enhanced fallback logic
        if self.score_raw is not None:
            # Check if it's already a percentage (0-100 range)
            if 0 <= self.score_raw <= 100:
                logger.info(f"SCORM: Using raw score as percentage: {self.score_raw}%")
                return self.score_raw
            # If it's a decimal (0-1 range), convert to percentage
            elif 0 <= self.score_raw <= 1:
                result = self.score_raw * 100
                logger.info(f"SCORM: Converted decimal to percentage: {result}%")
                return result
            # If it's a large number, assume it needs max score
            else:
                # Set default max score for percentage calculation
                if self.score_max is None:
                    self.score_max = 100  # Default max score
                    self.save()
                    logger.info(f"SCORM: Set default max score to 100")
                result = min(100, max(0, (self.score_raw / self.score_max) * 100))
                logger.info(f"SCORM: Calculated percentage with default max: {result}%")
                return result
        
        logger.warning(f"SCORM: No valid score data found for user {self.user.id}")
        return None
    
    def get_score_grade(self, pass_threshold=70):
        """Get letter grade based on percentage score"""
        percentage = self.get_score_percentage()
        if percentage is None:
            return "N/A"
        
        if percentage >= 90:
            return "A"
        elif percentage >= 80:
            return "B"
        elif percentage >= 70:
            return "C"
        elif percentage >= 60:
            return "D"
        else:
            return "F"
    
    def is_passing_score(self, pass_threshold=70):
        """Check if score meets passing threshold"""
        percentage = self.get_score_percentage()
        if percentage is None:
            return False
        return percentage >= pass_threshold
    
    def get_score_summary(self):
        """Get comprehensive score summary"""
        summary = {
            'raw_score': self.score_raw,
            'min_score': self.score_min,
            'max_score': self.score_max,
            'scaled_score': self.score_scaled,
            'percentage': self.get_score_percentage(),
            'grade': self.get_score_grade(),
            'is_passing': self.is_passing_score(),
            'is_valid': self.validate_score()
        }
        return summary
    
    def get_bookmark_data(self):
        """ENHANCED: Get bookmark and suspend data for resume functionality"""
        bookmark_data = {
            'lesson_location': self.raw_data.get('cmi.core.lesson_location', ''),
            'suspend_data': self.raw_data.get('cmi.core.suspend_data', ''),
            'entry': self.raw_data.get('cmi.core.entry', 'ab-initio'),
            'exit': self.raw_data.get('cmi.core.exit', ''),
            'launch_data': self.raw_data.get('cmi.core.launch_data', ''),
            'has_bookmark': bool(self.raw_data.get('cmi.core.lesson_location', '')),
            'has_suspend_data': bool(self.raw_data.get('cmi.core.suspend_data', '')),
            'can_resume': False
        }
        
        # ENHANCED: Check resume capability based on package type with proper field mapping
        if self.elearning_package.package_type == 'SCORM_1_2':
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('cmi.core.lesson_location', '') or 
                self.raw_data.get('cmi.core.suspend_data', '') or
                self.location or self.suspend_data
            )
        elif self.elearning_package.package_type == 'SCORM_2004':
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('cmi.location', '') or 
                self.raw_data.get('cmi.suspend_data', '') or
                self.raw_data.get('cmi.core.lesson_location', '') or 
                self.raw_data.get('cmi.core.suspend_data', '') or
                self.location or self.suspend_data
            )
        elif self.elearning_package.package_type == 'XAPI':
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('xapi.state', '') or 
                self.raw_data.get('xapi.activity_state', '') or
                self.raw_data.get('xapi.resume', False) or
                self.location or self.suspend_data
            )
        elif self.elearning_package.package_type == 'CMI5':
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('cmi5.au_state', '') or 
                self.raw_data.get('cmi5.state', '') or
                self.raw_data.get('cmi5.resume', False) or
                self.location or self.suspend_data
            )
        elif self.elearning_package.package_type == 'AICC':
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('aicc.lesson_location', '') or 
                self.raw_data.get('aicc.suspend_data', '') or
                self.location or self.suspend_data
            )
        else:
            # Default fallback
            bookmark_data['can_resume'] = bool(
                self.raw_data.get('cmi.core.lesson_location', '') or 
                self.raw_data.get('cmi.core.suspend_data', '') or
                self.location or self.suspend_data
            )
        
        return bookmark_data
    
    def set_bookmark(self, location, suspend_data=''):
        """Set bookmark data for resume functionality"""
        self.raw_data['cmi.core.lesson_location'] = location
        if suspend_data:
            self.raw_data['cmi.core.suspend_data'] = suspend_data
        self.raw_data['cmi.core.entry'] = 'resume'
        
        # FIXED: Also update the location field for easier querying
        self.location = location
        if suspend_data:
            self.suspend_data = suspend_data
            
        self.save()
        logger.info(f"SCORM: Bookmark set for user {self.user.id} at location: {location}")
    
    def clear_bookmark(self):
        """Clear bookmark data"""
        self.raw_data.pop('cmi.core.lesson_location', None)
        self.raw_data.pop('cmi.core.suspend_data', None)
        self.raw_data['cmi.core.entry'] = 'ab-initio'
        
        # FIXED: Also clear the location and suspend_data fields
        self.location = ''
        self.suspend_data = ''
        
        self.save()
        logger.info(f"SCORM: Bookmark cleared for user {self.user.id}")

    def check_mastery_completion(self):
        """Check if learner meets mastery score requirements for auto-completion"""
        if not self.student_data_mastery_score:
            return False
        
        # Get current score percentage
        score_percentage = self.get_score_percentage()
        if score_percentage is None:
            return False
        
        # Check if score meets or exceeds mastery score
        mastery_threshold = self.student_data_mastery_score
        if mastery_threshold <= 1.0:  # If mastery score is in 0-1 range
            mastery_threshold = mastery_threshold * 100  # Convert to percentage
        
        meets_mastery = score_percentage >= mastery_threshold
        
        if meets_mastery and self.completion_status != 'completed':
            self.completion_status = 'completed'
            self.success_status = 'passed'
            self.completion_date = timezone.now()
            self.save()
            
            # Sync to course progress
            self._sync_to_course_progress()
            
            logger.info(f"SCORM: Auto-completed based on mastery score. Score: {score_percentage}%, Mastery: {mastery_threshold}%")
            return True
        
        return False

    def _sync_to_course_progress(self):
        """Sync SCORM completion to course topic progress"""
        from courses.models import TopicProgress
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=self.user,
            topic=self.elearning_package.topic
        )
        
        if not topic_progress.completed:
            topic_progress.mark_complete('auto')
            logger.info(f"SCORM: Synced completion to course progress for user {self.user.id}, topic {self.elearning_package.topic.id}")

    def is_mastery_achieved(self):
        """Check if mastery score has been achieved"""
        if not self.student_data_mastery_score or not self.score_raw:
            return False
        
        score_percentage = self.get_score_percentage()
        if score_percentage is None:
            return False
        
        mastery_threshold = self.student_data_mastery_score
        if mastery_threshold <= 1.0:
            mastery_threshold = mastery_threshold * 100
        
        return score_percentage >= mastery_threshold

class SCORMReport(models.Model):
    """Model for SCORM reports and analytics"""
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='scorm_reports'
    )
    
    report_type = models.CharField(
        max_length=50,
        choices=[
            ('completion', 'Completion Report'),
            ('performance', 'Performance Report'),
            ('engagement', 'Engagement Report'),
            ('detailed', 'Detailed Report')
        ]
    )
    
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='generated_reports'
    )
    
    report_data = models.JSONField(
        default=dict,
        help_text="Report data and analytics"
    )
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return "{} - {}".format(self.course.title, self.get_report_type_display())

# Backward compatibility aliases removed - use ELearningPackage and ELearningTracking directly