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
from .storage import SCORMLocalStorage

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
        storage=SCORMLocalStorage(),
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
                # Local storage - use path directly
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
        """Find the main launch file based on package type"""
        launch_files = []
        
        if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
            launch_files = ['index.html', 'launch.html', 'start.html', 'main.html']
        elif self.package_type == 'XAPI':
            launch_files = ['index.html', 'launch.html', 'start.html', 'main.html', 'tincan.html']
        elif self.package_type == 'CMI5':
            launch_files = ['index.html', 'launch.html', 'start.html', 'main.html', 'cmi5.html']
        elif self.package_type == 'AICC':
            launch_files = ['index.html', 'launch.html', 'start.html', 'main.html']
        
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower() in [f.lower() for f in launch_files]:
                    return os.path.relpath(os.path.join(root, file), base_path)
        
        # If no common launch file found, look for HTML files
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith('.html'):
                    return os.path.relpath(os.path.join(root, file), base_path)
        
        return None
    
    def detect_package_type(self):
        """Detect the package type based on manifest files"""
        if not self.package_file:
            return None
        
        try:
            # Handle both local and remote storage
            if hasattr(self.package_file.storage, 'path'):
                # Local storage - use path directly
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
    
    # SCORM data model elements
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
    
    score_raw = models.FloatField(null=True, blank=True)
    score_min = models.FloatField(null=True, blank=True)
    score_max = models.FloatField(null=True, blank=True)
    score_scaled = models.FloatField(null=True, blank=True)
    
    progress_measure = models.FloatField(null=True, blank=True)
    
    # Time tracking
    total_time = models.DurationField(null=True, blank=True)
    session_time = models.DurationField(null=True, blank=True)
    
    # Additional data
    raw_data = models.JSONField(
        default=dict,
        help_text="Raw SCORM data from the package"
    )
    
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
        
        # Update scores
        if 'cmi.score.raw' in scorm_data:
            self.score_raw = float(scorm_data['cmi.score.raw']) if scorm_data['cmi.score.raw'] else None
        
        if 'cmi.score.min' in scorm_data:
            self.score_min = float(scorm_data['cmi.score.min']) if scorm_data['cmi.score.min'] else None
        
        if 'cmi.score.max' in scorm_data:
            self.score_max = float(scorm_data['cmi.score.max']) if scorm_data['cmi.score.max'] else None
        
        if 'cmi.score.scaled' in scorm_data:
            self.score_scaled = float(scorm_data['cmi.score.scaled']) if scorm_data['cmi.score.scaled'] else None
        
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
        """Parse SCORM time format (PT1H30M15S) to timedelta"""
        if not time_str or time_str == 'PT0S':
            return None
        
        try:
            # Remove PT prefix
            time_str = time_str[2:]
            
            hours = 0
            minutes = 0
            seconds = 0
            
            # Parse hours
            if 'H' in time_str:
                h_part = time_str.split('H')[0]
                hours = int(h_part)
                time_str = time_str.split('H')[1]
            
            # Parse minutes
            if 'M' in time_str:
                m_part = time_str.split('M')[0]
                minutes = int(m_part)
                time_str = time_str.split('M')[1]
            
            # Parse seconds
            if 'S' in time_str:
                s_part = time_str.split('S')[0]
                seconds = int(s_part)
            
            from datetime import timedelta
            return timedelta(hours=hours, minutes=minutes, seconds=seconds)
            
        except Exception as e:
            logger.error("Error parsing SCORM time: {} - {}".format(time_str, str(e)))
            return None
    
    def get_progress_percentage(self):
        """Get progress as percentage"""
        if self.progress_measure is not None:
            return min(100, max(0, self.progress_measure * 100))
        
        if self.completion_status == 'completed':
            return 100
        
        return 0
    
    def is_completed(self):
        """Check if the SCORM package is completed"""
        return self.completion_status == 'completed'
    
    def is_passed(self):
        """Check if the SCORM package is passed"""
        return self.success_status == 'passed'

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

# Backward compatibility aliases
SCORMPackage = ELearningPackage
SCORMTracking = ELearningTracking