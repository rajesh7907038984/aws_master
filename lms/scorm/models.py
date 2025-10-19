import os
import zipfile
import json
import logging
import traceback
from django.db import models
from django.conf import settings
# Removed unused default_storage import - using SCORMS3Storage instead
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
    from core.s3_storage import validate_s3_path, sanitize_s3_path
    
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
    
    full_path = "elearning/packages/{}".format(new_filename)
    
    # Validate and sanitize the path for S3 compatibility
    is_valid, error = validate_s3_path(full_path)
    if not is_valid:
        logger.warning(f"S3 path validation failed: {error}. Sanitizing path.")
        full_path = sanitize_s3_path(full_path)
    
    return full_path

class ELearningPackage(models.Model):
    """Model for e-learning packages (SCORM, xAPI, cmi5)"""
    
    PACKAGE_TYPES = [
        ('SCORM_1_2', 'SCORM 1.2'),
        ('SCORM_2004', 'SCORM 2004'),
        ('XAPI', 'xAPI (Tin Can)'),
        ('CMI5', 'cmi5'),
        ('AICC', 'AICC'),
        ('ARTICULATE', 'Articulate (Storyline/Rise)'),
        ('CAPTIVATE', 'Adobe Captivate'),
        ('LECTORA', 'Lectora'),
        ('ISPRING', 'iSpring'),
        ('ADOBE_PRESENTER', 'Adobe Presenter'),
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
        """Extract e-learning package DIRECTLY to S3 without using local disk storage"""
        try:
            if not self.package_file:
                error_msg = "No package file to extract"
                logger.error(error_msg)
                self.extraction_error = error_msg
                self.is_extracted = False
                self.save()
                return False
            
            # Enhanced file existence check
            if not self.package_file.storage.exists(self.package_file.name):
                error_msg = f"Package file not found in storage: {self.package_file.name}"
                logger.error(error_msg)
                self.extraction_error = error_msg
                self.is_extracted = False
                self.save()
                return False
            
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
            
            # Create topic-based directory structure for S3
            topic_dir = f"packages/{self.topic.id}"
            
            logger.info(f"SCORM: Starting DIRECT S3 extraction for topic {self.topic.id} - NO local disk usage")
            
            # Extract ZIP directly to S3 without local storage
            try:
                import io
                from django.core.files.base import ContentFile
                
                # Read ZIP file from S3 into memory
                logger.info(f"SCORM: Reading ZIP file from S3 into memory...")
                with self.package_file.open('rb') as source:
                    zip_data = source.read()
                
                # Open ZIP from memory
                zip_buffer = io.BytesIO(zip_data)
                
                # Validate ZIP file
                try:
                    with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                        # Test if ZIP is valid
                        bad_file = zip_ref.testzip()
                        if bad_file:
                            error_msg = f"Corrupted file in ZIP: {bad_file}"
                            logger.error(error_msg)
                            self.extraction_error = error_msg
                            self.is_extracted = False
                            self.save()
                            return False
                        
                        total_files = len(zip_ref.namelist())
                        logger.info(f"SCORM: ZIP validation passed - {total_files} files found")
                        
                except zipfile.BadZipFile as e:
                    error_msg = f"Invalid ZIP file format: {str(e)}"
                    logger.error(error_msg)
                    self.extraction_error = error_msg
                    self.is_extracted = False
                    self.save()
                    return False
                
                # Reset buffer position
                zip_buffer.seek(0)
                
                # Extract all files DIRECTLY to S3
                logger.info(f"SCORM: Extracting {total_files} files DIRECTLY to S3...")
                uploaded_count = 0
                failed_count = 0
                manifest_content = None
                manifest_filename = None
                all_files = []
                
                with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                    for file_info in zip_ref.infolist():
                        # Skip directories
                        if file_info.is_dir():
                            continue
                        
                        filename = file_info.filename
                        
                        # Security check: prevent path traversal
                        if '..' in filename or filename.startswith('/'):
                            logger.warning(f"SCORM: Skipping potentially unsafe file: {filename}")
                            failed_count += 1
                            continue
                        
                        try:
                            # Read file content from ZIP
                            file_content = zip_ref.read(filename)
                            
                            # Store all filenames for launch file detection
                            all_files.append(filename)
                            
                            # Check if this is a manifest file - store in memory for parsing
                            filename_lower = filename.lower()
                            if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
                                if filename_lower.endswith('imsmanifest.xml') or filename_lower.endswith('manifest.xml'):
                                    manifest_content = file_content
                                    manifest_filename = filename
                                    logger.info(f"SCORM: Found manifest file: {filename}")
                            elif self.package_type == 'XAPI':
                                if filename_lower.endswith('tincan.xml') or filename_lower.endswith('tincan.json'):
                                    manifest_content = file_content
                                    manifest_filename = filename
                            elif self.package_type == 'CMI5':
                                if filename_lower.endswith('cmi5.xml') or filename_lower.endswith('cmi5.json'):
                                    manifest_content = file_content
                                    manifest_filename = filename
                            elif self.package_type == 'AICC':
                                if filename_lower.endswith('.cst') or filename_lower.endswith('au.txt'):
                                    manifest_content = file_content
                                    manifest_filename = filename
                            
                            # Determine content type
                            content_type = self._get_enhanced_content_type(filename, filename)
                            
                            # Create S3 path
                            s3_path = f"{topic_dir}/{filename}"
                            
                            # Upload directly to S3
                            content_file = ContentFile(file_content)
                            self.package_file.storage.save(s3_path, content_file)
                            
                            uploaded_count += 1
                            
                            if uploaded_count % 100 == 0:
                                logger.info(f"SCORM: Uploaded {uploaded_count}/{total_files} files to S3...")
                            
                        except Exception as e:
                            logger.error(f"SCORM: Failed to upload {filename} to S3: {e}")
                            failed_count += 1
                
                logger.info(f"SCORM: Extraction complete - {uploaded_count} files uploaded, {failed_count} failed")
                
                # Validation: Check if any files were uploaded
                if uploaded_count == 0:
                    error_msg = "No files were successfully extracted to S3"
                    logger.error(error_msg)
                    self.extraction_error = error_msg
                    self.is_extracted = False
                    self.save()
                    return False
                
                # Parse manifest from memory if found
                if manifest_content and manifest_filename:
                    self.manifest_path = manifest_filename
                    try:
                        self._parse_manifest_from_content(manifest_content, manifest_filename)
                    except Exception as e:
                        logger.warning(f"SCORM: Failed to parse manifest: {e}")
                
                # Find launch file from extracted file list
                self.launch_file = self._find_launch_file_from_list(all_files)
                if self.launch_file:
                    logger.info(f"SCORM: Launch file detected: {self.launch_file} for package type {self.package_type}")
                    
                    # Verify launch file exists in S3
                    launch_path = f"{topic_dir}/{self.launch_file}"
                    if self.package_file.storage.exists(launch_path):
                        logger.info(f"SCORM: Verified launch file exists in S3: {launch_path}")
                    else:
                        logger.warning(f"SCORM: Launch file not found in S3: {launch_path}")
                else:
                    logger.warning(f"SCORM: No launch file found for package type {self.package_type}")
                
            except Exception as e:
                error_msg = f"Error during direct S3 extraction: {str(e)}"
                logger.error(error_msg)
                logger.error(f"Exception details: {traceback.format_exc()}")
                self.extraction_error = error_msg
                self.is_extracted = False
                self.save()
                return False
            
            # Set extraction status
            self.extracted_path = topic_dir
            self.is_extracted = True
            self.extraction_error = ""
            self.save()
            
            logger.info(f"SCORM: Successfully extracted {self.package_type} package for topic {self.topic.id} DIRECTLY to S3 (no local disk used)")
            return True
            
        except Exception as e:
            error_msg = f"Error extracting {getattr(self, 'package_type', 'unknown')} package: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Exception details: {traceback.format_exc()}")
            self.extraction_error = error_msg
            self.is_extracted = False
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
        """Parse SCORM manifest to extract metadata with enhanced error handling"""
        try:
            # Try to parse with different encodings
            encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
            tree = None
            
            for encoding in encodings:
                try:
                    with open(manifest_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    tree = ET.fromstring(content)
                    break
                except (UnicodeDecodeError, ET.ParseError):
                    continue
            
            if tree is None:
                logger.error(f"SCORM: Failed to parse manifest with any encoding: {manifest_path}")
                return
            
            # Handle different namespace versions
            namespaces = {
                'imscp': 'http://www.imsproject.org/xsd/imscp_rootv1p1p0',
                'imscp_v1p2': 'http://www.imsglobal.org/xsd/imscp_v1p1',
                'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2',
                'adlcp_v1p3': 'http://www.adlnet.org/xsd/adlcp_v1p3'
            }
            
            # Try to extract title with multiple namespace attempts
            title = ""
            for ns_prefix, ns_url in namespaces.items():
                try:
                    title_elem = tree.find(f'.//{{{ns_url}}}title')
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()
                        break
                except:
                    continue
            
            if not title:
                # Fallback to generic title search
                for elem in tree.iter():
                    if elem.tag.endswith('title') and elem.text:
                        title = elem.text.strip()
                        break
            
            self.title = title or "Untitled SCORM Package"
            
            # Extract description with multiple namespace attempts
            description = ""
            for ns_prefix, ns_url in namespaces.items():
                try:
                    desc_elem = tree.find(f'.//{{{ns_url}}}description')
                    if desc_elem is not None and desc_elem.text:
                        description = desc_elem.text.strip()
                        break
                except:
                    continue
            
            self.description = description or ""
            
            # Extract version
            version = ""
            for ns_prefix, ns_url in namespaces.items():
                try:
                    version_elem = tree.find(f'.//{{{ns_url}}}version')
                    if version_elem is not None and version_elem.text:
                        version = version_elem.text.strip()
                        break
                except:
                    continue
            
            self.version = version or "1.0"
            
            # Extract organization
            organization = ""
            for ns_prefix, ns_url in namespaces.items():
                try:
                    org_elem = tree.find(f'.//{{{ns_url}}}organization')
                    if org_elem is not None:
                        organization = org_elem.get('identifier', '') or org_elem.get('id', '')
                        if organization:
                            break
                except:
                    continue
            
            self.organization = organization or ""
            
            logger.info(f"SCORM: Successfully parsed manifest - Title: {self.title}, Version: {self.version}")
            
        except Exception as e:
            logger.error(f"SCORM: Error parsing SCORM manifest {manifest_path}: {e}")
            # Set default values on error
            self.title = "SCORM Package"
            self.description = ""
            self.version = "1.0"
            self.organization = ""
    
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
        """Find the main launch file based on package type with enhanced priority selection"""
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
    
    def _find_launch_file_from_list(self, file_list):
        """Find launch file from a list of filenames (for direct S3 extraction)"""
        if not file_list:
            return None
        
        # Define priority launch files based on package type
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
            ]
        elif self.package_type == 'XAPI':
            launch_files = [
                'tincan.html',
                'launch.html',
                'player.html',
                'index.html',
                'start.html',
                'main.html',
            ]
        elif self.package_type == 'CMI5':
            launch_files = [
                'cmi5.html',
                'au.html',
                'launch.html',
                'player.html',
                'index.html',
                'start.html',
                'main.html',
            ]
        elif self.package_type == 'AICC':
            launch_files = [
                'au.html',
                'launch.html',
                'player.html',
                'index.html',
                'start.html',
                'main.html',
            ]
        
        # Search for priority files first
        for preferred_file in launch_files:
            for file_path in file_list:
                if file_path.lower() == preferred_file.lower() or file_path.lower().endswith('/' + preferred_file.lower()):
                    logger.info(f"SCORM: Selected launch file '{file_path}' (priority: {preferred_file}) for package type {self.package_type}")
                    return file_path
        
        # Fallback: find any HTML file
        for file_path in file_list:
            if file_path.lower().endswith('.html'):
                logger.info(f"SCORM: Using fallback HTML launch file '{file_path}' for package type {self.package_type}")
                return file_path
        
        logger.warning(f"SCORM: No launch file found for package type {self.package_type}")
        return None
    
    def _parse_manifest_from_content(self, manifest_content, manifest_filename):
        """Parse manifest from in-memory content (for direct S3 extraction)"""
        try:
            if self.package_type in ['SCORM_1_2', 'SCORM_2004']:
                self._parse_scorm_manifest_from_content(manifest_content)
            elif self.package_type == 'XAPI':
                self._parse_xapi_manifest_from_content(manifest_content, manifest_filename)
            elif self.package_type == 'CMI5':
                self._parse_cmi5_manifest_from_content(manifest_content, manifest_filename)
            elif self.package_type == 'AICC':
                self._parse_aicc_manifest_from_content(manifest_content)
            
            self.save()
            
        except Exception as e:
            logger.error(f"SCORM: Error parsing {self.package_type} manifest from memory: {e}")
    
    def _parse_scorm_manifest_from_content(self, manifest_content):
        """Parse SCORM manifest from memory content"""
        try:
            # Try to parse with different encodings
            encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
            tree = None
            
            for encoding in encodings:
                try:
                    content_str = manifest_content.decode(encoding) if isinstance(manifest_content, bytes) else manifest_content
                    tree = ET.fromstring(content_str)
                    break
                except (UnicodeDecodeError, ET.ParseError):
                    continue
            
            if tree is None:
                logger.error(f"SCORM: Failed to parse manifest with any encoding")
                return
            
            # Handle different namespace versions
            namespaces = {
                'imscp': 'http://www.imsglobal.org/xsd/imscp_v1p1',
                'adlcp': 'http://www.adlnet.org/xsd/adlcp_v1p3',
                'lom': 'http://ltsc.ieee.org/xsd/LOM'
            }
            
            # Try to extract title
            title_elem = tree.find('.//imscp:title', namespaces)
            if title_elem is not None and title_elem.text:
                self.title = title_elem.text
            else:
                # Try without namespace
                title_elem = tree.find('.//title')
                if title_elem is not None and title_elem.text:
                    self.title = title_elem.text
            
            # Try to extract version
            metadata_elem = tree.find('.//imscp:metadata', namespaces)
            if metadata_elem is not None:
                schema_version = metadata_elem.find('.//imscp:schemaversion', namespaces)
                if schema_version is not None and schema_version.text:
                    self.version = schema_version.text
            
            logger.info(f"SCORM: Parsed manifest successfully - Title: {self.title}, Version: {self.version}")
            
        except Exception as e:
            logger.error(f"SCORM: Error parsing SCORM manifest from content: {e}")
    
    def _parse_xapi_manifest_from_content(self, manifest_content, manifest_filename):
        """Parse xAPI manifest from memory content"""
        try:
            if manifest_filename.lower().endswith('.json'):
                import json
                content_str = manifest_content.decode('utf-8') if isinstance(manifest_content, bytes) else manifest_content
                data = json.loads(content_str)
                self.title = data.get('name', {}).get('en-US', self.title)
                self.description = data.get('description', {}).get('en-US', '')
            else:
                # Parse XML
                content_str = manifest_content.decode('utf-8') if isinstance(manifest_content, bytes) else manifest_content
                tree = ET.fromstring(content_str)
                title_elem = tree.find('.//title')
                if title_elem is not None:
                    self.title = title_elem.text
            
            logger.info(f"SCORM: Parsed xAPI manifest - Title: {self.title}")
        except Exception as e:
            logger.error(f"SCORM: Error parsing xAPI manifest: {e}")
    
    def _parse_cmi5_manifest_from_content(self, manifest_content, manifest_filename):
        """Parse cmi5 manifest from memory content"""
        try:
            if manifest_filename.lower().endswith('.json'):
                import json
                content_str = manifest_content.decode('utf-8') if isinstance(manifest_content, bytes) else manifest_content
                data = json.loads(content_str)
                self.title = data.get('title', {}).get('en-US', self.title)
                self.cmi5_au_id = data.get('id', '')
            else:
                # Parse XML
                content_str = manifest_content.decode('utf-8') if isinstance(manifest_content, bytes) else manifest_content
                tree = ET.fromstring(content_str)
                title_elem = tree.find('.//title')
                if title_elem is not None:
                    self.title = title_elem.text
            
            logger.info(f"SCORM: Parsed cmi5 manifest - Title: {self.title}")
        except Exception as e:
            logger.error(f"SCORM: Error parsing cmi5 manifest: {e}")
    
    def _parse_aicc_manifest_from_content(self, manifest_content):
        """Parse AICC manifest from memory content"""
        try:
            content_str = manifest_content.decode('utf-8') if isinstance(manifest_content, bytes) else manifest_content
            lines = content_str.split('\n')
            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key == 'course_title':
                        self.title = value
                    elif key == 'course_id':
                        self.version = value
            
            logger.info(f"SCORM: Parsed AICC manifest - Title: {self.title}")
        except Exception as e:
            logger.error(f"SCORM: Error parsing AICC manifest: {e}")
    
    def _upload_extracted_content_to_s3(self, local_path, s3_topic_dir):
        """Upload extracted SCORM content to S3 with enhanced validation, streaming, and security"""
        try:
            from django.core.files.base import ContentFile
            import mimetypes
            import time
            import hashlib
            
            # Validation: Check if local path exists
            if not os.path.exists(local_path):
                error_msg = f"Local extraction path does not exist: {local_path}"
                logger.error(f"SCORM: {error_msg}")
                raise FileNotFoundError(error_msg)
            
            # Count files to upload and calculate total size
            total_files = 0
            total_size = 0
            large_files = []
            
            for root, dirs, files in os.walk(local_path):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    file_size = os.path.getsize(local_file_path)
                    total_size += file_size
                    total_files += 1
                    
                    # Track large files (>100MB) for streaming upload
                    if file_size > 100 * 1024 * 1024:  # 100MB
                        large_files.append((local_file_path, file_size))
            
            if total_files == 0:
                error_msg = f"No files found in extraction directory: {local_path}"
                logger.error(f"SCORM: {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"SCORM: Uploading {total_files} files ({total_size / (1024*1024):.1f}MB) to S3 for topic {self.topic.id}")
            
            uploaded_count = 0
            failed_count = 0
            failed_files = []
            
            # Walk through all files in the extracted directory
            for root, dirs, files in os.walk(local_path):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    file_size = os.path.getsize(local_file_path)
                    
                    # Calculate relative path from the extraction directory
                    rel_path = os.path.relpath(local_file_path, local_path)
                    # Normalize path separators for S3 (use forward slashes)
                    rel_path = rel_path.replace(os.sep, '/')
                    s3_file_path = f"{s3_topic_dir}/{rel_path}"
                    
                    # Security validation: Check for path traversal
                    if '..' in rel_path or rel_path.startswith('/'):
                        logger.error(f"SCORM: Security violation - path traversal detected: {rel_path}")
                        failed_count += 1
                        failed_files.append((rel_path, "Path traversal security violation"))
                        continue
                    
                    # Determine content type with enhanced detection
                    content_type = self._get_enhanced_content_type(local_file_path, file)
                    
                    # Upload to S3 with enhanced retry logic and streaming for large files
                    upload_success = False
                    
                    if file_size > 100 * 1024 * 1024:  # 100MB threshold
                        # Use streaming upload for large files
                        upload_success = self._upload_large_file_streaming(
                            local_file_path, s3_file_path, content_type, rel_path
                        )
                    else:
                        # Use regular upload for smaller files
                        upload_success = self._upload_small_file_regular(
                            local_file_path, s3_file_path, content_type, rel_path
                        )
                    
                    if upload_success:
                        uploaded_count += 1
                        logger.debug(f"SCORM: Uploaded {rel_path} to S3 as {s3_file_path}")
                    else:
                        failed_count += 1
                        failed_files.append((rel_path, "Upload failed after all retries"))
            
            # Validation: Check upload success
            if uploaded_count == 0:
                error_msg = f"Failed to upload any files to S3 for topic {self.topic.id}"
                logger.error(f"SCORM: {error_msg}")
                raise Exception(error_msg)
            
            # Log summary
            logger.info(f"SCORM: Upload complete for topic {self.topic.id}: {uploaded_count}/{total_files} files uploaded successfully")
            
            if failed_count > 0:
                logger.warning(f"SCORM: {failed_count} files failed to upload:")
                for failed_file, error in failed_files[:10]:  # Log first 10 failures
                    logger.warning(f"  - {failed_file}: {error}")
                
                # If more than 50% of files failed, treat as critical error
                if failed_count > (total_files * 0.5):
                    error_msg = f"More than 50% of files failed to upload ({failed_count}/{total_files})"
                    logger.error(f"SCORM: {error_msg}")
                    raise Exception(error_msg)
            
            # Verify extraction: Check if key files exist in S3
            if self.launch_file:
                launch_path = f"{s3_topic_dir}/{self.launch_file}"
                if not self.package_file.storage.exists(launch_path):
                    error_msg = f"Launch file not found in S3 after upload: {launch_path}"
                    logger.error(f"SCORM: {error_msg}")
                    raise FileNotFoundError(error_msg)
                logger.info(f"SCORM: Verified launch file exists in S3: {launch_path}")
            
            logger.info(f"SCORM: Successfully uploaded and verified extracted content for topic {self.topic.id} to S3")
            
        except Exception as e:
            logger.error(f"SCORM: Error uploading extracted content to S3: {e}")
            raise
    
    def _get_enhanced_content_type(self, file_path, filename):
        """Enhanced content type detection with SCORM-specific types"""
        import mimetypes
        
        # Get base content type
        content_type, _ = mimetypes.guess_type(file_path)
        
        if not content_type:
            # Enhanced detection for SCORM-specific files
            if filename.lower().endswith('.html') or filename.lower().endswith('.htm'):
                content_type = 'text/html; charset=utf-8'
            elif filename.lower().endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif filename.lower().endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif filename.lower().endswith('.json'):
                content_type = 'application/json; charset=utf-8'
            elif filename.lower().endswith('.xml'):
                content_type = 'application/xml; charset=utf-8'
            elif filename.lower().endswith('.png'):
                content_type = 'image/png'
            elif filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif filename.lower().endswith('.gif'):
                content_type = 'image/gif'
            elif filename.lower().endswith('.svg'):
                content_type = 'image/svg+xml'
            elif filename.lower().endswith('.woff'):
                content_type = 'font/woff'
            elif filename.lower().endswith('.woff2'):
                content_type = 'font/woff2'
            elif filename.lower().endswith('.ttf'):
                content_type = 'font/ttf'
            elif filename.lower().endswith('.eot'):
                content_type = 'application/vnd.ms-fontobject'
            elif filename.lower().endswith('.otf'):
                content_type = 'font/otf'
            elif filename.lower().endswith('.mp4'):
                content_type = 'video/mp4'
            elif filename.lower().endswith('.webm'):
                content_type = 'video/webm'
            elif filename.lower().endswith('.ogg'):
                content_type = 'video/ogg'
            elif filename.lower().endswith('.mp3'):
                content_type = 'audio/mpeg'
            elif filename.lower().endswith('.wav'):
                content_type = 'audio/wav'
            elif filename.lower().endswith('.swf'):
                content_type = 'application/x-shockwave-flash'
            else:
                content_type = 'application/octet-stream'
        
        return content_type
    
    def _upload_small_file_regular(self, local_file_path, s3_file_path, content_type, rel_path):
        """Upload small files using regular Django storage"""
        from django.core.files.base import ContentFile
        import time
        
        max_retries = 3
        retry_count = 0
        upload_success = False
        
        while retry_count < max_retries and not upload_success:
            try:
                with open(local_file_path, 'rb') as f:
                    content = f.read()
                
                content_file = ContentFile(content)
                self.package_file.storage.save(s3_file_path, content_file)
                upload_success = True
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"SCORM: Error uploading {rel_path} to S3 after {max_retries} attempts: {e}")
                else:
                    logger.warning(f"SCORM: Retry {retry_count}/{max_retries} for {rel_path}: {e}")
                    time.sleep(2 ** retry_count)  # Exponential backoff
        
        return upload_success
    
    def _upload_large_file_streaming(self, local_file_path, s3_file_path, content_type, rel_path):
        """Upload large files using streaming to avoid memory issues"""
        import boto3
        from django.conf import settings
        import time
        
        try:
            # Use boto3 directly for multipart upload
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            key = f"elearning/{s3_file_path}"
            
            # Configure multipart upload
            config = boto3.s3.transfer.TransferConfig(
                multipart_threshold=1024 * 25,  # 25MB
                max_concurrency=10,
                multipart_chunksize=1024 * 25,  # 25MB chunks
                use_threads=True
            )
            
            # Upload with progress tracking
            s3_client.upload_file(
                local_file_path,
                bucket_name,
                key,
                ExtraArgs={'ContentType': content_type},
                Config=config
            )
            
            logger.info(f"SCORM: Successfully streamed large file {rel_path} to S3")
            return True
            
        except Exception as e:
            logger.error(f"SCORM: Error streaming large file {rel_path} to S3: {e}")
            return False
    
    def _validate_zip_security(self, zip_path):
        """Validate ZIP file for security issues - ENHANCED with better error handling"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                total_size = 0
                file_count = 0
                max_files = 50000  # Increased limit for large e-learning packages
                max_total_size = 2 * 1024 * 1024 * 1024  # 2GB limit (increased for large packages)
                max_file_size = 500 * 1024 * 1024  # 500MB per file (increased for large media files)
                
                for info in zip_ref.infolist():
                    file_count += 1
                    total_size += info.file_size
                    
                    # Check for path traversal - more lenient for e-learning content
                    if '..' in info.filename and not any(allowed in info.filename.lower() for allowed in ['../', '..\\']):
                        # Allow some common e-learning path patterns
                        if not any(pattern in info.filename.lower() for pattern in ['content/', 'media/', 'assets/', 'images/', 'videos/', 'audio/']):
                            logger.warning(f"SCORM: Potential path traversal in ZIP: {info.filename}")
                            # Don't fail immediately, just log warning
                    
                    # Check for excessive file count (ZIP bomb protection) - more lenient
                    if file_count > max_files:
                        logger.error(f"SCORM: Too many files in ZIP: {file_count}")
                        return False
                    
                    # Check for excessive total size - more lenient
                    if total_size > max_total_size:
                        logger.error(f"SCORM: ZIP too large: {total_size} bytes")
                        return False
                    
                    # Check for individual large files - more lenient for media files
                    if info.file_size > max_file_size:
                        # Allow large media files
                        if not any(ext in info.filename.lower() for ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.mp3', '.wav', '.aac', '.m4a']):
                            logger.error(f"SCORM: File too large: {info.filename} ({info.file_size} bytes)")
                            return False
                        else:
                            logger.info(f"SCORM: Allowing large media file: {info.filename} ({info.file_size} bytes)")
                    
                    # Check for suspicious file names - more lenient for e-learning content
                    suspicious_patterns = [
                        'cmd.exe', 'powershell.exe', 'bash', 'sh', 'bat', 'ps1',
                        'system32', 'windows', 'etc/passwd', 'etc/shadow'
                    ]
                    
                    filename_lower = info.filename.lower()
                    for pattern in suspicious_patterns:
                        if pattern in filename_lower:
                            # Allow some common e-learning patterns that might contain these keywords
                            if not any(allowed in filename_lower for allowed in ['content/', 'media/', 'assets/', 'images/', 'videos/', 'audio/', 'scorm/', 'elearning/']):
                                logger.error(f"SCORM: Suspicious file in ZIP: {info.filename}")
                                return False
                            else:
                                logger.info(f"SCORM: Allowing e-learning file with suspicious pattern: {info.filename}")
                
                logger.info(f"SCORM: ZIP security validation passed: {file_count} files, {total_size} bytes")
                return True
                
        except zipfile.BadZipFile as e:
            logger.error(f"SCORM: Invalid ZIP file format: {e}")
            return False
        except Exception as e:
            logger.error(f"SCORM: Error validating ZIP security: {e}")
            return False
    
    def _extract_zip_secure(self, zip_ref, target_dir):
        """Extract ZIP file with security checks"""
        import os.path
        
        for info in zip_ref.infolist():
            # Additional security check during extraction
            if '..' in info.filename or info.filename.startswith('/'):
                logger.error(f"SCORM: Path traversal blocked during extraction: {info.filename}")
                continue
            
            # Ensure extracted path is within target directory
            target_path = os.path.join(target_dir, info.filename)
            if not target_path.startswith(target_dir):
                logger.error(f"SCORM: Extraction path outside target directory: {info.filename}")
                continue
            
            # Extract file
            try:
                zip_ref.extract(info, target_dir)
            except Exception as e:
                logger.warning(f"SCORM: Failed to extract {info.filename}: {e}")
                continue
    
    def _cleanup_temp_files(self, zip_path, full_topic_dir):
        """Enhanced cleanup with retry logic and race condition handling"""
        import time
        import stat
        
        # Clean up temp ZIP file
        if zip_path and os.path.exists(zip_path):
            for attempt in range(3):
                try:
                    # Make file writable if it's read-only
                    if os.path.exists(zip_path):
                        os.chmod(zip_path, stat.S_IWRITE)
                    os.unlink(zip_path)
                    logger.debug(f"SCORM: Cleaned up temp file {zip_path}")
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f"SCORM: Cleanup attempt {attempt + 1} failed for {zip_path}: {e}")
                        time.sleep(1)
                    else:
                        logger.error(f"SCORM: Failed to clean up temp file {zip_path} after 3 attempts: {e}")
        
        # Clean up temp extraction directory
        if full_topic_dir and os.path.exists(full_topic_dir):
            for attempt in range(3):
                try:
                    # Make directory and contents writable
                    for root, dirs, files in os.walk(full_topic_dir):
                        for d in dirs:
                            try:
                                os.chmod(os.path.join(root, d), stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                            except:
                                pass
                        for f in files:
                            try:
                                os.chmod(os.path.join(root, f), stat.S_IWRITE | stat.S_IREAD)
                            except:
                                pass
                    
                    shutil.rmtree(full_topic_dir)
                    logger.debug(f"SCORM: Cleaned up temp directory {full_topic_dir}")
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f"SCORM: Cleanup attempt {attempt + 1} failed for {full_topic_dir}: {e}")
                        time.sleep(2)
                    else:
                        logger.error(f"SCORM: Failed to clean up temp directory {full_topic_dir} after 3 attempts: {e}")
                        # Try to remove individual files as fallback
                        try:
                            for root, dirs, files in os.walk(full_topic_dir, topdown=False):
                                for file in files:
                                    try:
                                        os.remove(os.path.join(root, file))
                                    except:
                                        pass
                                for dir in dirs:
                                    try:
                                        os.rmdir(os.path.join(root, dir))
                                    except:
                                        pass
                        except:
                            pass
    
    def detect_package_type(self):
        """Detect the package type based on manifest files - S3 compatible"""
        if not self.package_file:
            return None
        
        zip_path = None
        cleanup_temp = False
        
        try:
            # For S3 storage, always download to temp file first
            # S3 storage returns S3 key for .path, not a local file path
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
                cleanup_temp = True
            
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
                    except Exception as e:
                        logger.warning(f"Error determining SCORM version: {e}")
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
                
                # ENHANCED: Check for Articulate content
                elif any('story_content' in f.lower() or 'story_html5' in f.lower() for f in file_list):
                    return 'ARTICULATE'
                
                # Check for Rise content
                elif any('rise_content' in f.lower() or 'rise_html5' in f.lower() for f in file_list):
                    return 'ARTICULATE'
                
                # Check for Captivate content
                elif any('captivate' in f.lower() or 'cp_' in f.lower() for f in file_list):
                    return 'CAPTIVATE'
                
                # Check for Lectora content
                elif any('lectora' in f.lower() or 'trivantis' in f.lower() for f in file_list):
                    return 'LECTORA'
                
                # Check for iSpring content
                elif any('ispring' in f.lower() or 'ispring_content' in f.lower() for f in file_list):
                    return 'ISPRING'
                
                # Check for Adobe Presenter content
                elif any('presenter' in f.lower() or 'adobe_presenter' in f.lower() for f in file_list):
                    return 'ADOBE_PRESENTER'
            
            # Return None as default (no recognized package type)
            return None
                
        except Exception as e:
            logger.error("Error detecting package type: {}".format(str(e)))
            return None
        finally:
            # Always clean up temp file if we created one
            if cleanup_temp and zip_path and os.path.exists(zip_path):
                try:
                    os.unlink(zip_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temp file {zip_path}: {cleanup_error}")
    
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
    
    def validate_s3_path(self):
        """Validate and fix S3 path construction"""
        if self.extracted_path and self.extracted_path.startswith('elearning/'):
            # Fix double prefixing issue
            self.extracted_path = self.extracted_path.replace('elearning/', '')
            self.save()
            logger.info(f"Fixed double prefixing for topic {self.topic.id}: {self.extracted_path}")
        return self.extracted_path
    
    def validate_extraction(self):
        """Validate SCORM package extraction and S3 storage"""
        issues = []
        
        # Check package file
        if not self.package_file:
            issues.append("No package file")
        elif not self.package_file.storage.exists(self.package_file.name):
            issues.append("Package file not found in S3")
        
        # Check extraction status
        if not self.is_extracted:
            issues.append("Package not extracted")
        
        # Check extracted path
        if not self.extracted_path:
            issues.append("No extracted path")
        elif not self.package_file.storage.exists(self.extracted_path):
            issues.append("Extracted content not found in S3")
        
        # Check launch file
        if not self.launch_file:
            issues.append("No launch file")
        elif self.extracted_path:
            launch_path = f"{self.extracted_path}/{self.launch_file}"
            if not self.package_file.storage.exists(launch_path):
                issues.append("Launch file not found in S3")
        
        # Check package type
        if not self.package_type:
            issues.append("No package type specified")
        
        return len(issues) == 0, issues
    
    def fix_extraction(self):
        """Fix SCORM package extraction issues"""
        try:
            logger.info(f"SCORM: Fixing extraction for topic {self.topic.id}")
            
            # Reset extraction status
            self.is_extracted = False
            self.extraction_error = ""
            self.save()
            
            # Re-extract the package
            result = self.extract_package()
            
            if result:
                # Validate the extraction
                is_valid, issues = self.validate_extraction()
                if is_valid:
                    logger.info(f"SCORM: Successfully fixed extraction for topic {self.topic.id}")
                    return True
                else:
                    logger.error(f"SCORM: Extraction completed but validation failed for topic {self.topic.id}: {issues}")
                    return False
            else:
                logger.error(f"SCORM: Failed to extract package for topic {self.topic.id}")
                return False
                
        except Exception as e:
            logger.error(f"SCORM: Error fixing extraction for topic {self.topic.id}: {e}")
            return False


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
                    logger.warning("SCORM: Error parsing hours from: {{original_time_str}}")
            
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
                    logger.info("SCORM: Set default max score to 100")
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
        """FIXED: Get bookmark and suspend data for resume functionality with consistent logic"""
        bookmark_data = {
            'lesson_location': '',
            'suspend_data': '',
            'entry': 'ab-initio',
            'exit': '',
            'launch_data': '',
            'has_bookmark': False,
            'has_suspend_data': False,
            'can_resume': False,
            'package_type': self.elearning_package.package_type,
            'progress_indicators': []
        }
        
        # FIXED: Consistent resume detection logic across all package types
        package_type = self.elearning_package.package_type
        
        # Get common resume indicators
        has_progress = self.completion_status not in ['not attempted', 'unknown']
        has_time = self.total_time and self.total_time.total_seconds() > 0
        has_score = self.score_raw is not None and self.score_raw > 0
        has_location = bool(self.location)
        has_suspend_data = bool(self.suspend_data)
        
        if package_type in ['SCORM_1_2', 'SCORM_2004']:
            # SCORM packages - use both raw_data and model fields
            lesson_location = (
                self.raw_data.get('cmi.core.lesson_location', '') or 
                self.raw_data.get('cmi.location', '') or 
                self.location
            )
            suspend_data = (
                self.raw_data.get('cmi.core.suspend_data', '') or 
                self.raw_data.get('cmi.suspend_data', '') or 
                self.suspend_data
            )
            
            bookmark_data.update({
                'lesson_location': lesson_location,
                'suspend_data': suspend_data,
                'entry': self.raw_data.get('cmi.core.entry', 'ab-initio'),
                'exit': self.raw_data.get('cmi.core.exit', ''),
                'launch_data': self.raw_data.get('cmi.core.launch_data', ''),
            })
            
            has_lesson_location = bool(lesson_location)
            has_suspend_data = bool(suspend_data)
            has_exit_suspend = bookmark_data['exit'] == 'suspend'
            
            bookmark_data['progress_indicators'] = [
                f"Lesson Location: {has_lesson_location}",
                f"Suspend Data: {has_suspend_data}",
                f"Progress: {has_progress}",
                f"Time: {has_time}",
                f"Score: {has_score}",
                f"Exit Suspend: {has_exit_suspend}"
            ]
            
            bookmark_data['can_resume'] = (
                has_lesson_location or has_suspend_data or 
                has_progress or has_time or has_score or 
                has_exit_suspend or has_location or has_suspend_data
            )
            
        elif package_type == 'XAPI':
            # xAPI packages
            lesson_location = self.raw_data.get('xapi.state', '')
            suspend_data = self.raw_data.get('xapi.activity_state', '')
            
            bookmark_data.update({
                'lesson_location': lesson_location,
                'suspend_data': suspend_data,
                'entry': 'ab-initio',
                'exit': '',
                'launch_data': '',
            })
            
            has_lesson_location = bool(lesson_location)
            has_suspend_data = bool(suspend_data)
            has_resume_flag = self.raw_data.get('xapi.resume', False)
            
            bookmark_data['progress_indicators'] = [
                f"xAPI State: {has_lesson_location}",
                f"Activity State: {has_suspend_data}",
                f"Resume Flag: {has_resume_flag}",
                f"Progress: {has_progress}",
                f"Time: {has_time}",
                f"Score: {has_score}"
            ]
            
            bookmark_data['can_resume'] = (
                has_lesson_location or has_suspend_data or has_resume_flag or
                has_progress or has_time or has_score or 
                has_location or has_suspend_data
            )
            
        elif package_type == 'CMI5':
            # cmi5 packages
            lesson_location = self.raw_data.get('cmi5.au_state', '')
            suspend_data = self.raw_data.get('cmi5.state', '')
            
            bookmark_data.update({
                'lesson_location': lesson_location,
                'suspend_data': suspend_data,
                'entry': 'ab-initio',
                'exit': '',
                'launch_data': '',
            })
            
            has_lesson_location = bool(lesson_location)
            has_suspend_data = bool(suspend_data)
            has_resume_flag = self.raw_data.get('cmi5.resume', False)
            
            bookmark_data['progress_indicators'] = [
                f"AU State: {has_lesson_location}",
                f"cmi5 State: {has_suspend_data}",
                f"Resume Flag: {has_resume_flag}",
                f"Progress: {has_progress}",
                f"Time: {has_time}",
                f"Score: {has_score}"
            ]
            
            bookmark_data['can_resume'] = (
                has_lesson_location or has_suspend_data or has_resume_flag or
                has_progress or has_time or has_score or 
                has_location or has_suspend_data
            )
            
        else:
            # Default fallback for unknown package types
            lesson_location = (
                self.raw_data.get('cmi.core.lesson_location', '') or 
                self.location
            )
            suspend_data = (
                self.raw_data.get('cmi.core.suspend_data', '') or 
                self.suspend_data
            )
            
            bookmark_data.update({
                'lesson_location': lesson_location,
                'suspend_data': suspend_data,
                'entry': self.raw_data.get('cmi.core.entry', 'ab-initio'),
                'exit': self.raw_data.get('cmi.core.exit', ''),
                'launch_data': self.raw_data.get('cmi.core.launch_data', ''),
            })
            
            has_lesson_location = bool(lesson_location)
            has_suspend_data = bool(suspend_data)
            
            bookmark_data['progress_indicators'] = [
                f"Lesson Location: {has_lesson_location}",
                f"Suspend Data: {has_suspend_data}",
                f"Progress: {has_progress}",
                f"Time: {has_time}",
                f"Score: {has_score}"
            ]
            
            bookmark_data['can_resume'] = (
                has_lesson_location or has_suspend_data or
                has_progress or has_time or has_score or 
                has_location or has_suspend_data
            )
        
        # Set common fields
        bookmark_data['has_bookmark'] = bool(bookmark_data['lesson_location'])
        bookmark_data['has_suspend_data'] = bool(bookmark_data['suspend_data'])
        
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

    def get_articulate_bookmark_data(self):
        """
        ENHANCED: Articulate-specific bookmark data extraction with comprehensive support.
        Handles Storyline, Rise, Presenter, Quizmaker, and Articulate 360 packages.
        """
        articulate_bookmarks = {
            'storyline': {},
            'rise': {},
            'presenter': {},
            'quizmaker': {},
            'generic': {},
            'can_resume': False,
            'package_type': 'Articulate',
            'progress_indicators': []
        }
        
        try:
            if not self.raw_data:
                return articulate_bookmarks
            
            # ENHANCED: Articulate Storyline bookmark detection
            storyline_indicators = [
                'articulate.bookmark',
                'articulate.storyline.bookmark',
                'articulate.storyline.slide',
                'articulate.storyline.scene',
                'articulate.storyline.state',
                'articulate.storyline.progress'
            ]
            
            for indicator in storyline_indicators:
                if indicator in self.raw_data:
                    articulate_bookmarks['storyline'][indicator] = self.raw_data[indicator]
            
            # ENHANCED: Articulate Rise bookmark detection
            rise_indicators = [
                'articulate.rise.bookmark',
                'articulate.rise.lesson',
                'articulate.rise.block',
                'articulate.rise.progress',
                'articulate.rise.state',
                'articulate.rise.navigation'
            ]
            
            for indicator in rise_indicators:
                if indicator in self.raw_data:
                    articulate_bookmarks['rise'][indicator] = self.raw_data[indicator]
            
            # ENHANCED: Articulate Presenter bookmark detection
            presenter_indicators = [
                'articulate.presenter.bookmark',
                'articulate.presenter.slide',
                'articulate.presenter.timeline',
                'articulate.presenter.state',
                'articulate.presenter.progress'
            ]
            
            for indicator in presenter_indicators:
                if indicator in self.raw_data:
                    articulate_bookmarks['presenter'][indicator] = self.raw_data[indicator]
            
            # ENHANCED: Articulate Quizmaker bookmark detection
            quizmaker_indicators = [
                'articulate.quizmaker.bookmark',
                'articulate.quizmaker.question',
                'articulate.quizmaker.answer',
                'articulate.quizmaker.state',
                'articulate.quizmaker.progress'
            ]
            
            for indicator in quizmaker_indicators:
                if indicator in self.raw_data:
                    articulate_bookmarks['quizmaker'][indicator] = self.raw_data[indicator]
            
            # ENHANCED: Generic Articulate bookmark detection
            generic_indicators = [
                'articulate.bookmark_data',
                'articulate.suspend_data',
                'articulate.lesson_location',
                'articulate.progress',
                'articulate.navigation',
                'articulate.state',
                'articulate.resume'
            ]
            
            for indicator in generic_indicators:
                if indicator in self.raw_data:
                    articulate_bookmarks['generic'][indicator] = self.raw_data[indicator]
            
            # ENHANCED: Resume capability detection for Articulate packages
            has_storyline_bookmark = bool(articulate_bookmarks['storyline'])
            has_rise_bookmark = bool(articulate_bookmarks['rise'])
            has_presenter_bookmark = bool(articulate_bookmarks['presenter'])
            has_quizmaker_bookmark = bool(articulate_bookmarks['quizmaker'])
            has_generic_bookmark = bool(articulate_bookmarks['generic'])
            
            # Check for standard SCORM fields that might be Articulate-specific
            has_lesson_location = bool(self.raw_data.get('cmi.core.lesson_location', ''))
            has_suspend_data = bool(self.raw_data.get('cmi.core.suspend_data', ''))
            has_progress = self.completion_status not in ['not attempted', 'unknown']
            has_time = self.total_time and self.total_time.total_seconds() > 0
            has_score = self.score_raw is not None and self.score_raw > 0
            
            articulate_bookmarks['progress_indicators'] = [
                f"Storyline Bookmark: {has_storyline_bookmark}",
                f"Rise Bookmark: {has_rise_bookmark}",
                f"Presenter Bookmark: {has_presenter_bookmark}",
                f"Quizmaker Bookmark: {has_quizmaker_bookmark}",
                f"Generic Bookmark: {has_generic_bookmark}",
                f"Lesson Location: {has_lesson_location}",
                f"Suspend Data: {has_suspend_data}",
                f"Progress: {has_progress}",
                f"Time: {has_time}",
                f"Score: {has_score}"
            ]
            
            # Determine if Articulate package can resume
            articulate_bookmarks['can_resume'] = (
                has_storyline_bookmark or has_rise_bookmark or 
                has_presenter_bookmark or has_quizmaker_bookmark or
                has_generic_bookmark or has_lesson_location or 
                has_suspend_data or has_progress or has_time or 
                has_score or self.location or self.suspend_data
            )
            
            return articulate_bookmarks
            
        except Exception as e:
            logger.error(f"SCORM: Error extracting Articulate bookmark data: {str(e)}")
            return {
                'storyline': {},
                'rise': {},
                'presenter': {},
                'quizmaker': {},
                'generic': {},
                'can_resume': False,
                'package_type': 'Articulate',
                'progress_indicators': [f"Error: {str(e)}"]
            }

    def validate_data_size(self, data, package_type):
        """
        ENHANCED: Validate data size limits for different SCORM package types.
        Prevents data truncation and ensures proper resume functionality.
        """
        try:
            if not data:
                return True, "No data to validate"
            
            data_size = len(str(data))
            
            if package_type == 'SCORM_1_2':
                max_size = 4096  # 4KB limit for SCORM 1.2
                if data_size > max_size:
                    logger.warning(f"SCORM 1.2: Data size {data_size} exceeds limit of {max_size} bytes")
                    return False, f"Data size {data_size} bytes exceeds SCORM 1.2 limit of {max_size} bytes"
                    
            elif package_type == 'SCORM_2004':
                max_size = 64000  # 64KB limit for SCORM 2004
                if data_size > max_size:
                    logger.warning(f"SCORM 2004: Data size {data_size} exceeds limit of {max_size} bytes")
                    return False, f"Data size {data_size} bytes exceeds SCORM 2004 limit of {max_size} bytes"
                    
            elif package_type in ['XAPI', 'CMI5']:
                # xAPI and cmi5 have much larger limits (practically unlimited)
                max_size = 1000000  # 1MB practical limit
                if data_size > max_size:
                    logger.warning(f"{package_type}: Data size {data_size} exceeds practical limit of {max_size} bytes")
                    return False, f"Data size {data_size} bytes exceeds practical limit of {max_size} bytes"
                    
            else:
                # Default fallback
                max_size = 64000
                if data_size > max_size:
                    logger.warning(f"Unknown package type {package_type}: Data size {data_size} exceeds default limit of {max_size} bytes")
                    return False, f"Data size {data_size} bytes exceeds default limit of {max_size} bytes"
            
            return True, f"Data size {data_size} bytes is within limits"
            
        except Exception as e:
            logger.error(f"Error validating data size: {str(e)}")
            return False, f"Error validating data size: {str(e)}"

    def set_bookmark_with_validation(self, location, suspend_data=''):
        """
        ENHANCED: Set bookmark data with size validation for different package types.
        Automatically handles data truncation if necessary.
        """
        try:
            package_type = self.elearning_package.package_type
            
            # Validate location data
            location_valid, location_msg = self.validate_data_size(location, package_type)
            if not location_valid:
                logger.warning(f"SCORM: Location data validation failed: {location_msg}")
                # Truncate if necessary
                if package_type == 'SCORM_1_2':
                    location = location[:4000]  # Leave some buffer
                elif package_type == 'SCORM_2004':
                    location = location[:63000]  # Leave some buffer
            
            # Validate suspend data
            suspend_valid, suspend_msg = self.validate_data_size(suspend_data, package_type)
            if not suspend_valid:
                logger.warning(f"SCORM: Suspend data validation failed: {suspend_msg}")
                # Truncate if necessary
                if package_type == 'SCORM_1_2':
                    suspend_data = suspend_data[:4000]  # Leave some buffer
                elif package_type == 'SCORM_2004':
                    suspend_data = suspend_data[:63000]  # Leave some buffer
            
            # Set the bookmark data
            self.raw_data['cmi.core.lesson_location'] = location
            if suspend_data:
                self.raw_data['cmi.core.suspend_data'] = suspend_data
            self.raw_data['cmi.core.entry'] = 'resume'
            
            # Also update the location field for easier querying
            self.location = location
            if suspend_data:
                self.suspend_data = suspend_data
                
            self.save()
            logger.info(f"SCORM: Bookmark set for user {self.user.id} at location: {location} (validated for {package_type})")
            
            return True, "Bookmark set successfully"
            
        except Exception as e:
            logger.error(f"SCORM: Error setting bookmark with validation: {str(e)}")
            return False, f"Error setting bookmark: {str(e)}"

    def _find_articulate_launch_file(self):
        """
        Enhanced Articulate launch file detection.
        Handles various Articulate package structures and file naming conventions.
        """
        try:
            if not self.elearning_package.extracted_path:
                return None
            
            from .storage import SCORMS3Storage
            storage = SCORMS3Storage()
            
            # Get the extracted directory contents
            files, dirs = storage.listdir(self.elearning_package.extracted_path)
            
            # Priority list of Articulate launch files
            articulate_launch_files = [
                # Articulate Storyline files
                'story.html',
                'story.html5',
                'story_html5.html',
                'storyline.html',
                'storyline.html5',
                'storyline_html5.html',
                'storyline_story.html',
                'storyline_story_html5.html',
                'storyline_story_html5_story.html',
                
                # Articulate Rise files
                'rise.html',
                'rise.html5',
                'rise_html5.html',
                'rise_story.html',
                'rise_story_html5.html',
                
                # Articulate Presenter files
                'presenter.html',
                'presenter.html5',
                'presenter_html5.html',
                'presenter_story.html',
                'presenter_story_html5.html',
                
                # Articulate Quizmaker files
                'quizmaker.html',
                'quizmaker.html5',
                'quizmaker_html5.html',
                'quizmaker_story.html',
                'quizmaker_story_html5.html',
                
                # Generic Articulate files
                'articulate.html',
                'articulate.html5',
                'articulate_html5.html',
                'articulate_story.html',
                'articulate_story_html5.html',
                
                # Common HTML files that might be Articulate
                'index.html',
                'main.html',
                'content.html',
                'launch.html',
                'player.html',
                'story.html',
                'story_html5.html',
                'story_html5_story.html',
                'story_html5_story_html5.html',
                'story_html5_story_html5_story.html',
            ]
            
            # Check for exact matches first
            for launch_file in articulate_launch_files:
                if launch_file in files:
                    return f"{self.elearning_package.extracted_path}/{launch_file}"
            
            # Check for files that start with Articulate keywords
            for file in files:
                if file.lower().startswith(('story', 'rise', 'presenter', 'quizmaker', 'articulate')):
                    if file.lower().endswith(('.html', '.htm')):
                        return f"{self.elearning_package.extracted_path}/{file}"
            
            # Check for files that contain Articulate keywords
            for file in files:
                if any(keyword in file.lower() for keyword in ['story', 'rise', 'presenter', 'quizmaker', 'articulate']):
                    if file.lower().endswith(('.html', '.htm')):
                        return f"{self.elearning_package.extracted_path}/{file}"
            
            # Fallback: Check for any HTML file
            for file in files:
                if file.lower().endswith(('.html', '.htm')):
                    return f"{self.elearning_package.extracted_path}/{file}"
            
            return None
            
        except Exception as e:
            logger.error(f"SCORM: Error finding Articulate launch file: {str(e)}")
            return None

    def _is_articulate_file(self, file_path):
        """
        Check if a file is an Articulate package file.
        """
        try:
            if not file_path:
                return False
            
            file_name = file_path.lower()
            
            # Check for Articulate-specific file patterns
            articulate_patterns = [
                'story.html',
                'rise.html',
                'presenter.html',
                'quizmaker.html',
                'articulate.html',
                'story_html5.html',
                'rise_html5.html',
                'presenter_html5.html',
                'quizmaker_html5.html',
                'articulate_html5.html',
                'storyline.html',
                'storyline_html5.html',
                'storyline_story.html',
                'storyline_story_html5.html',
                'storyline_story_html5_story.html',
            ]
            
            # Check for exact matches
            if file_name in articulate_patterns:
                return True
            
            # Check for partial matches
            for pattern in articulate_patterns:
                if pattern in file_name:
                    return True
            
            # Check for Articulate keywords
            articulate_keywords = ['story', 'rise', 'presenter', 'quizmaker', 'articulate', 'storyline']
            for keyword in articulate_keywords:
                if keyword in file_name:
                    return True
            
            return False
            
        except Exception as e:
            logger.error("SCORM: Error checking Articulate file: {{str(e)}}")
            return False

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
