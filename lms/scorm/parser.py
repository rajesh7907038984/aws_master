"""
SCORM Package Parser
Handles SCORM 1.2 and SCORM 2004 package parsing without external APIs
Stores extracted content to S3
Includes comprehensive validation before processing
"""
import os
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import logging
import uuid
import json
from .validators import validate_scorm_package, ScormValidationError
from .mastery_score_handler import MasteryScoreExtractor

logger = logging.getLogger(__name__)


class ScormParser:
    """Parse SCORM packages and extract metadata"""
    
    # SCORM namespace definitions
    NAMESPACES = {
        '1.2': {
            'default': 'http://www.imsproject.org/xsd/imscp_rootv1p1p2',
            'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2'
        },
        '2004': {
            'default': 'http://www.imsglobal.org/xsd/imscp_v1p1',
            'adlcp': 'http://www.adlnet.org/xsd/adlcp_v1p3',
            'adlseq': 'http://www.adlnet.org/xsd/adlseq_v1p3',
            'adlnav': 'http://www.adlnet.org/xsd/adlnav_v1p3',
            'imsss': 'http://www.imsglobal.org/xsd/imsss'
        }
    }
    
    def __init__(self, uploaded_file):
        """
        Initialize parser with uploaded SCORM package
        
        Args:
            uploaded_file: Django UploadedFile object
        """
        self.uploaded_file = uploaded_file
        self.manifest_data = {}
        self.version = None
        self.launch_url = None
        
    def parse(self, skip_validation=False):
        """
        Parse SCORM package and extract to S3
        
        Args:
            skip_validation: If True, skip validation checks (for testing)
        
        Returns:
            dict: Package information including version, launch_url, manifest_data, extracted_path
        """
        # Validate package before processing (unless skipped)
        if not skip_validation:
            logger.info("Validating SCORM package before parsing...")
            validation_results = validate_scorm_package(self.uploaded_file)
            
            if not validation_results['valid']:
                error_msg = f"SCORM package validation failed: {'; '.join(validation_results['errors'])}"
                logger.error(error_msg)
                raise ScormValidationError(error_msg, validation_results['errors'])
            
            if validation_results['warnings']:
                logger.warning(f"SCORM package has warnings: {'; '.join(validation_results['warnings'])}")
            
            logger.info(f"SCORM package validation passed: {validation_results['info']}")
        
        # Generate unique identifier for this package
        package_id = str(uuid.uuid4())
        base_path = f'scorm_content/{package_id}'
        
        # Read the zip file
        zip_buffer = BytesIO(self.uploaded_file.read())
        
        with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
            # First, find and parse the manifest
            manifest_content = None
            manifest_file = None
            
            # Look for manifest files (imsmanifest.xml or tincan.xml)
            manifest_file = None
            manifest_content = None
            
            for file_name in zip_ref.namelist():
                if file_name.lower().endswith('imsmanifest.xml'):
                    manifest_file = file_name
                    manifest_content = zip_ref.read(file_name)
                    self.version = 'scorm'  # Will be determined later
                    break
                elif file_name.lower().endswith('tincan.xml'):
                    manifest_file = file_name
                    manifest_content = zip_ref.read(file_name)
                    self.version = 'xapi'
                    break
            
            # If no standard manifest found, try to detect package type from content
            if not manifest_content:
                package_type = self._detect_package_type(zip_ref)
                if package_type:
                    self.version = package_type
                    logger.info(f"Detected package type: {package_type}")
                else:
                    raise ValueError("No manifest file found and unable to detect package type")
            
            # Parse the manifest if available
            if manifest_content:
                self._parse_manifest(manifest_content)
            else:
                # Handle packages without manifests
                self._handle_legacy_package(zip_ref)
            
            # Extract all files to S3
            extracted_files = []
            for file_name in zip_ref.namelist():
                if file_name.endswith('/'):
                    # Skip directories
                    continue
                
                file_data = zip_ref.read(file_name)
                
                # Determine the S3 path
                # If manifest was in a subdirectory, preserve the structure
                if manifest_file and '/' in manifest_file:
                    manifest_dir = os.path.dirname(manifest_file)
                    # Remove manifest directory from file path
                    if file_name.startswith(manifest_dir):
                        relative_path = file_name[len(manifest_dir):].lstrip('/')
                    else:
                        relative_path = file_name
                else:
                    relative_path = file_name
                
                s3_path = f'{base_path}/{relative_path}'
                
                # Upload to S3
                default_storage.save(s3_path, ContentFile(file_data))
                extracted_files.append(relative_path)
                
                logger.info(f"Uploaded {relative_path} to S3: {s3_path}")
            
            # Adjust launch URL if manifest was in subdirectory
            if manifest_file and '/' in manifest_file:
                manifest_dir = os.path.dirname(manifest_file)
                if self.launch_url and not self.launch_url.startswith(manifest_dir):
                    # Launch URL is relative to manifest location
                    pass
            
            # CRITICAL FIX: If launch URL is not set or is index_lms.html, check for story.html
            # story.html is the correct player file for Articulate Storyline packages
            if not self.launch_url or self.launch_url == 'index_lms.html':
                # Check if story.html exists in extracted files
                story_html_candidates = [f for f in extracted_files if f.lower().endswith('story.html')]
                if story_html_candidates:
                    self.launch_url = story_html_candidates[0]
                    logger.info(f"Using story.html as launch file: {self.launch_url}")
                elif not self.launch_url:
                    # Fallback to other common entry points (prioritize story.html)
                    entry_points = ['story.html', 'index.html', 'launch.html', 'start.html', 'main.html']
                    for entry_point in entry_points:
                        candidates = [f for f in extracted_files if f.lower().endswith(entry_point)]
                        if candidates:
                            self.launch_url = candidates[0]
                            logger.info(f"Using {entry_point} as launch file: {self.launch_url}")
                            break
            
            return {
                'version': self.version,
                'launch_url': self.launch_url,
                'manifest_data': self.manifest_data,
                'extracted_path': base_path,
                'identifier': self.manifest_data.get('identifier', package_id),
                'title': self.manifest_data.get('title', 'SCORM Course'),
                'description': self.manifest_data.get('description', ''),
                'mastery_score': self.manifest_data.get('mastery_score'),
                'extracted_files': extracted_files
            }
    
    def _parse_manifest(self, manifest_content):
        """
        Parse imsmanifest.xml or tincan.xml to extract metadata
        
        Args:
            manifest_content: XML content as bytes
        """
        try:
            root = ET.fromstring(manifest_content)
            
            # Check if this is a Tin Can/xAPI package
            if root.tag.lower().endswith('tincan') or 'tincan' in root.tag.lower():
                self._parse_tincan_manifest(root)
                return
            
            # Detect SCORM version
            self.version = self._detect_version(root)
            
            # Get namespaces for this version
            ns = self.NAMESPACES.get(self.version, self.NAMESPACES['1.2'])
            
            # Extract package metadata
            self.manifest_data['identifier'] = root.get('identifier', '')
            
            # Get metadata
            metadata = root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}metadata') or \
                      root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}metadata') or \
                      root.find('.//metadata')
            
            if metadata is not None:
                # Try to get title and description from metadata
                schema_elem = metadata.find('.//{http://www.imsglobal.org/xsd/imsmd_v1p2}general') or \
                             metadata.find('.//general')
                
                if schema_elem is not None:
                    title_elem = schema_elem.find('.//{http://www.imsglobal.org/xsd/imsmd_v1p2}title') or \
                                schema_elem.find('.//title')
                    if title_elem is not None:
                        title_text = title_elem.find('.//{http://www.imsglobal.org/xsd/imsmd_v1p2}langstring') or \
                                    title_elem.find('.//langstring')
                        if title_text is not None and title_text.text:
                            self.manifest_data['title'] = title_text.text.strip()
            
            # Get organizations
            organizations = root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}organizations') or \
                          root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}organizations') or \
                          root.find('.//organizations')
            
            if organizations is not None:
                # Get default organization
                default_org = organizations.get('default', '')
                organization = organizations.find(f'.//*[@identifier="{default_org}"]') if default_org else \
                             organizations.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}organization') or \
                             organizations.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}organization') or \
                             organizations.find('.//organization')
                
                if organization is not None:
                    # Get organization title if not already set
                    if 'title' not in self.manifest_data:
                        title = organization.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}title') or \
                               organization.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}title') or \
                               organization.find('.//title')
                        if title is not None and title.text:
                            self.manifest_data['title'] = title.text.strip()
                    
                    # Parse items to find launch URL
                    items = organization.findall('.//{http://www.imsglobal.org/xsd/imscp_v1p1}item') or \
                           organization.findall('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}item') or \
                           organization.findall('.//item')
                    
                    if items:
                        # Get the first item's identifierref
                        first_item = items[0]
                        identifierref = first_item.get('identifierref', '')
                        
                        # Try to get mastery score
                        if self.version == '1.2':
                            # SCORM 1.2: Look for adlcp:masteryscore
                            mastery_score = first_item.find('.//{http://www.adlnet.org/xsd/adlcp_rootv1p2}masteryscore') or \
                                          first_item.find('.//adlcp:masteryscore', namespaces={'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2'}) or \
                                          first_item.find('.//masteryscore') or \
                                          first_item.find('.//{http://www.adlnet.org/xsd/adlcp_rootv1p2}mastery_score') or \
                                          first_item.find('.//mastery_score')
                            if mastery_score is not None and mastery_score.text:
                                try:
                                    score = float(mastery_score.text)
                                    # Ensure it's in percentage (0-100) range
                                    if 0 <= score <= 1:
                                        score = score * 100  # Convert decimal to percentage
                                    self.manifest_data['mastery_score'] = score
                                    logger.info(f"Extracted SCORM 1.2 mastery score: {score}%")
                                except ValueError:
                                    pass
                        elif self.version == '2004':
                            # SCORM 2004: Look for imsss:minNormalizedMeasure in sequencing rules
                            sequencing = first_item.find('.//{http://www.imsglobal.org/xsd/imsss}sequencing') or \
                                       first_item.find('.//imsss:sequencing', namespaces={'imsss': 'http://www.imsglobal.org/xsd/imsss'}) or \
                                       first_item.find('.//sequencing')
                            if sequencing is not None:
                                # Look for completion threshold or objectives
                                min_normalized = sequencing.find('.//{http://www.imsglobal.org/xsd/imsss}minNormalizedMeasure') or \
                                               sequencing.find('.//imsss:minNormalizedMeasure', namespaces={'imsss': 'http://www.imsglobal.org/xsd/imsss'}) or \
                                               sequencing.find('.//minNormalizedMeasure')
                                
                                if min_normalized is not None and min_normalized.text:
                                    try:
                                        score = float(min_normalized.text)
                                        # SCORM 2004 uses 0-1 scale, convert to percentage
                                        if 0 <= score <= 1:
                                            score = score * 100
                                        self.manifest_data['mastery_score'] = score
                                        logger.info(f"Extracted SCORM 2004 mastery score: {score}%")
                                    except ValueError:
                                        pass
                                
                                # Alternative: Look for completion threshold
                                if 'mastery_score' not in self.manifest_data:
                                    completion_threshold = sequencing.find('.//{http://www.imsglobal.org/xsd/imsss}completionThreshold') or \
                                                         sequencing.find('.//imsss:completionThreshold', namespaces={'imsss': 'http://www.imsglobal.org/xsd/imsss'}) or \
                                                         sequencing.find('.//completionThreshold')
                                    
                                    if completion_threshold is not None:
                                        min_progress = completion_threshold.get('minProgressMeasure') or completion_threshold.get('completedByMeasure')
                                        if min_progress:
                                            try:
                                                score = float(min_progress)
                                                if 0 <= score <= 1:
                                                    score = score * 100
                                                self.manifest_data['mastery_score'] = score
                                                logger.info(f"Extracted SCORM 2004 completion threshold: {score}%")
                                            except ValueError:
                                                pass
                        
                        # Use the comprehensive mastery score extractor
                        if 'mastery_score' not in self.manifest_data:
                            package_filename = getattr(self.uploaded_file, 'name', '')
                            mastery_score = MasteryScoreExtractor.extract_mastery_score(
                                manifest_content, 
                                package_filename
                            )
                            if mastery_score is not None:
                                self.manifest_data['mastery_score'] = mastery_score
                                logger.info(f"Extracted mastery score using comprehensive handler: {mastery_score}%")
                            else:
                                logger.info("No mastery score found in SCORM manifest - will use course default")
                        
                        # Find corresponding resource
                        if identifierref:
                            resources = root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}resources') or \
                                      root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}resources') or \
                                      root.find('.//resources')
                            
                            if resources is not None:
                                resource = resources.find(f'.//*[@identifier="{identifierref}"]')
                                if resource is not None:
                                    self.launch_url = resource.get('href', '')
            
            # Fallback: if no launch URL found, look for common entry points
            if not self.launch_url:
                resources = root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}resources') or \
                          root.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}resources') or \
                          root.find('.//resources')
                
                if resources is not None:
                    resource = resources.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}resource') or \
                             resources.find('.//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}resource') or \
                             resources.find('.//resource')
                    
                    if resource is not None:
                        self.launch_url = resource.get('href', '')
            
            # Final fallback to common file names
            if not self.launch_url:
                self.launch_url = 'index.html'
            
            # Store raw manifest data
            self.manifest_data['raw_manifest'] = manifest_content.decode('utf-8', errors='ignore')
            
            logger.info(f"Parsed SCORM {self.version} package: {self.manifest_data.get('title')}")
            logger.info(f"Launch URL: {self.launch_url}")
            
        except ET.ParseError as e:
            logger.error(f"Error parsing manifest XML: {str(e)}")
            raise ValueError(f"Invalid SCORM manifest: {str(e)}")
    
    def _detect_version(self, root):
        """
        Detect SCORM version from manifest
        
        Args:
            root: XML root element
            
        Returns:
            str: SCORM version ('1.2' or '2004')
        """
        # Check namespace
        if 'imscp_v1p1' in str(root.tag):
            return '2004'
        elif 'imscp_rootv1p1p2' in str(root.tag):
            return '1.2'
        
        # Check schema version
        metadata = root.find('.//metadata')
        if metadata is not None:
            schema = metadata.find('.//schema')
            if schema is not None and schema.text:
                if '2004' in schema.text:
                    return '2004'
                elif '1.2' in schema.text:
                    return '1.2'
        
        # Check for SCORM 2004 specific elements
        if root.find('.//{http://www.adlnet.org/xsd/adlseq_v1p3}sequencing') is not None:
            return '2004'
        
        # Default to SCORM 1.2
        return '1.2'
    
    def _parse_tincan_manifest(self, root):
        """
        Parse tincan.xml to extract xAPI/Tin Can metadata
        
        Args:
            root: XML root element
        """
        try:
            # Set version to xAPI
            self.version = 'xapi'
            
            # Extract basic metadata from tincan.xml
            self.manifest_data['identifier'] = root.get('id', '')
            
            # Look for activities (they should be under <activities> element)
            activities_container = root.find('.//activities')
            if activities_container is not None:
                activities = activities_container.findall('.//activity')
            else:
                activities = []
            
            if activities:
                # Use the first activity as the main content
                main_activity = activities[0]
                
                # Get activity name
                name_elem = main_activity.find('.//name')
                if name_elem is not None:
                    langstring = name_elem.find('.//langstring')
                    if langstring is not None and langstring.text:
                        self.manifest_data['title'] = langstring.text.strip()
                
                # Get activity description
                description_elem = main_activity.find('.//description')
                if description_elem is not None:
                    desc_langstring = description_elem.find('.//langstring')
                    if desc_langstring is not None and desc_langstring.text:
                        self.manifest_data['description'] = desc_langstring.text.strip()
                
                # Get launch URL from the <launch> element
                launch_elem = main_activity.find('.//launch')
                if launch_elem is not None and launch_elem.text:
                    self.launch_url = launch_elem.text.strip()
                    logger.info(f"Found launch URL in tincan.xml: {self.launch_url}")
                
                # Look for launch URL in extensions if not found
                if not self.launch_url:
                    extensions = main_activity.find('.//extensions')
                    if extensions is not None:
                        # Look for common launch URL patterns
                        for ext in extensions.findall('.//*'):
                            if ext.text and ('index.html' in ext.text or 'story.html' in ext.text or 'launch' in ext.text.lower()):
                                self.launch_url = ext.text.strip()
                                break
            
            # If no launch URL found, look for common entry points
            if not self.launch_url:
                # Common xAPI entry points - prioritize story.html for Articulate Storyline
                common_entry_points = ['story.html', 'index.html', 'launch.html', 'start.html']
                # This will be handled in the file extraction process
            
            logger.info(f"Parsed Tin Can/xAPI manifest: {self.manifest_data.get('title', 'Untitled')}")
            
        except Exception as e:
            logger.error(f"Error parsing Tin Can manifest: {e}")
            raise ValueError(f"Failed to parse tincan.xml: {e}")
    
    def _detect_package_type(self, zip_ref):
        """
        Detect package type from content when no manifest is found
        
        Args:
            zip_ref: ZipFile object
            
        Returns:
            str: Detected package type or None
        """
        try:
            file_list = zip_ref.namelist()
            
            # Check for common SCORM package indicators
            has_html = any(f.lower().endswith(('.html', '.htm')) for f in file_list)
            has_js = any(f.lower().endswith('.js') for f in file_list)
            has_css = any(f.lower().endswith('.css') for f in file_list)
            
            # Check for specific authoring tool indicators
            if any('storyline' in f.lower() for f in file_list):
                return 'storyline'
            elif any('captivate' in f.lower() for f in file_list):
                return 'captivate'
            elif any('lectora' in f.lower() for f in file_list):
                return 'lectora'
            elif any('html5' in f.lower() for f in file_list):
                return 'html5'
            elif any('scorm' in f.lower() for f in file_list):
                return 'legacy'
            
            # Check for common entry points
            entry_points = ['index.html', 'story.html', 'launch.html', 'start.html', 'main.html']
            for entry_point in entry_points:
                if any(f.lower().endswith(entry_point) for f in file_list):
                    if has_html and (has_js or has_css):
                        return 'html5'
                    else:
                        return 'legacy'
            
            # If it has HTML content but no clear indicators, assume it's a legacy package
            if has_html:
                return 'legacy'
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting package type: {e}")
            return None
    
    def _handle_legacy_package(self, zip_ref):
        """
        Handle legacy SCORM packages without proper manifests
        
        Args:
            zip_ref: ZipFile object
        """
        try:
            file_list = zip_ref.namelist()
            
            # Set basic metadata for legacy packages
            self.manifest_data['identifier'] = f"legacy_{uuid.uuid4().hex[:8]}"
            self.manifest_data['title'] = 'Legacy SCORM Package'
            self.manifest_data['description'] = 'Legacy SCORM package without manifest'
            
            # Find the launch URL by looking for common entry points
            # Prioritize story.html for Articulate Storyline packages
            entry_points = ['story.html', 'index.html', 'launch.html', 'start.html', 'main.html', 'default.html']
            for entry_point in entry_points:
                for file_name in file_list:
                    if file_name.lower().endswith(entry_point):
                        self.launch_url = file_name
                        logger.info(f"Found launch URL for legacy package: {self.launch_url}")
                        return
            
            # If no standard entry point found, use the first HTML file
            html_files = [f for f in file_list if f.lower().endswith(('.html', '.htm'))]
            if html_files:
                self.launch_url = html_files[0]
                logger.info(f"Using first HTML file as launch URL: {self.launch_url}")
            else:
                # If no HTML files, use the first file
                if file_list:
                    self.launch_url = file_list[0]
                    logger.warning(f"No HTML files found, using first file as launch URL: {self.launch_url}")
                else:
                    raise ValueError("No files found in package")
            
            logger.info(f"Handled legacy package: {self.manifest_data.get('title', 'Untitled')}")
            
        except Exception as e:
            logger.error(f"Error handling legacy package: {e}")
            raise ValueError(f"Failed to handle legacy package: {e}")

