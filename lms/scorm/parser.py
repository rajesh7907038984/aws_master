"""
SCORM Package Parser
Handles SCORM 1.2 and SCORM 2004 package parsing without external APIs
Stores extracted content to S3
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
        
    def parse(self):
        """
        Parse SCORM package and extract to S3
        
        Returns:
            dict: Package information including version, launch_url, manifest_data, extracted_path
        """
        # Generate unique identifier for this package
        package_id = str(uuid.uuid4())
        base_path = f'scorm_content/{package_id}'
        
        # Read the zip file
        zip_buffer = BytesIO(self.uploaded_file.read())
        
        with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
            # First, find and parse the manifest
            manifest_content = None
            manifest_file = None
            
            # Look for imsmanifest.xml in root or subdirectories
            for file_name in zip_ref.namelist():
                if file_name.lower().endswith('imsmanifest.xml'):
                    manifest_file = file_name
                    manifest_content = zip_ref.read(file_name)
                    break
            
            if not manifest_content:
                raise ValueError("No imsmanifest.xml found in SCORM package")
            
            # Parse the manifest
            self._parse_manifest(manifest_content)
            
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
        Parse imsmanifest.xml to extract metadata
        
        Args:
            manifest_content: XML content as bytes
        """
        try:
            root = ET.fromstring(manifest_content)
            
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
                            mastery_score = first_item.find('.//{http://www.adlnet.org/xsd/adlcp_rootv1p2}masteryscore') or \
                                          first_item.find('.//masteryscore')
                            if mastery_score is not None and mastery_score.text:
                                try:
                                    self.manifest_data['mastery_score'] = float(mastery_score.text)
                                except ValueError:
                                    pass
                        
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

