"""
SCORM Package Validators
Provides validation utilities for SCORM packages before processing
"""
import os
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class ScormValidationError(Exception):
    """Custom exception for SCORM validation errors"""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


class ScormPackageValidator:
    """
    Comprehensive SCORM package validator
    Validates packages before processing to prevent errors
    """
    
    # Required files for SCORM packages (either imsmanifest.xml or tincan.xml)
    REQUIRED_FILES = ['imsmanifest.xml', 'tincan.xml']
    
    # Common SCORM file extensions
    ALLOWED_EXTENSIONS = [
        '.html', '.htm', '.js', '.css', '.json', '.xml',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp',
        '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv',
        '.pdf', '.doc', '.docx', '.ppt', '.pptx',
        '.swf', '.flv',  # Legacy Flash content
        '.woff', '.woff2', '.ttf', '.eot',  # Fonts
        '.zip'  # Nested archives (some SCORM packages)
    ]
    
    # Suspicious file extensions that should be flagged
    SUSPICIOUS_EXTENSIONS = [
        '.exe', '.bat', '.cmd', '.com', '.scr', '.pif',
        '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
        '.ps1', '.psm1', '.psd1', '.ps1xml', '.pssc', '.psc1',
        '.msi', '.msp', '.mst', '.reg', '.hta'
    ]
    
    # Maximum file size (600MB)
    MAX_PACKAGE_SIZE = 600 * 1024 * 1024  # 600MB (was 500MB)
    
    # Maximum number of files
    MAX_FILES = 10000
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
    def validate_package(self, uploaded_file) -> Dict:
        """
        Validate a SCORM package thoroughly
        
        Args:
            uploaded_file: Django UploadedFile object
            
        Returns:
            dict: Validation results with status, errors, warnings, and metadata
        """
        self.errors = []
        self.warnings = []
        self.info = []
        
        try:
            # Reset file position
            uploaded_file.seek(0)
            
            # Basic file checks
            self._validate_file_basics(uploaded_file)
            
            # Create BytesIO for zip processing
            file_buffer = BytesIO(uploaded_file.read())
            uploaded_file.seek(0)  # Reset for later use
            
            # Validate ZIP structure
            file_list = self._validate_zip_structure(file_buffer)
            
            # Validate manifest
            manifest_data = self._validate_manifest(file_buffer, file_list)
            
            # Security checks
            self._validate_security(file_list)
            
            # Performance checks
            self._validate_performance(file_list, file_buffer)
            
            # Determine overall status
            status = 'valid' if not self.errors else 'invalid'
            if self.warnings and status == 'valid':
                status = 'valid_with_warnings'
            
            return {
                'status': status,
                'valid': len(self.errors) == 0,
                'errors': self.errors,
                'warnings': self.warnings,
                'info': self.info,
                'manifest_data': manifest_data,
                'file_count': len(file_list),
                'estimated_size': uploaded_file.size
            }
            
        except Exception as e:
            logger.error(f"Error during SCORM validation: {str(e)}")
            self.errors.append(f"Validation error: {str(e)}")
            return {
                'status': 'error',
                'valid': False,
                'errors': self.errors,
                'warnings': self.warnings,
                'info': self.info,
                'manifest_data': None
            }
    
    def _validate_file_basics(self, uploaded_file):
        """Validate basic file properties"""
        # Check file size
        if uploaded_file.size > self.MAX_PACKAGE_SIZE:
            self.errors.append(f"Package too large: {uploaded_file.size / (1024*1024):.1f}MB (max: {self.MAX_PACKAGE_SIZE / (1024*1024):.0f}MB)")
        
        # Check file extension
        if not uploaded_file.name.lower().endswith('.zip'):
            self.warnings.append("File extension is not .zip - this may not be a SCORM package")
        
        self.info.append(f"Package size: {uploaded_file.size / (1024*1024):.1f}MB")
    
    def _validate_zip_structure(self, file_buffer) -> List[str]:
        """Validate ZIP file structure and return file list"""
        try:
            with zipfile.ZipFile(file_buffer, 'r') as zip_ref:
                # Test ZIP integrity
                try:
                    zip_ref.testzip()
                except Exception as e:
                    self.errors.append(f"Corrupted ZIP file: {str(e)}")
                    return []
                
                # Get file list
                file_list = zip_ref.namelist()
                
                # Check file count
                if len(file_list) > self.MAX_FILES:
                    self.errors.append(f"Too many files: {len(file_list)} (max: {self.MAX_FILES})")
                
                # Check for required files (either imsmanifest.xml or tincan.xml)
                manifest_found = any(f.lower().endswith(('imsmanifest.xml', 'tincan.xml')) for f in file_list)
                if not manifest_found:
                    # Check if it's a legacy package with HTML content
                    html_files = [f for f in file_list if f.lower().endswith(('.html', '.htm'))]
                    if html_files:
                        self.warnings.append("No manifest file found - treating as legacy SCORM package")
                        self.info.append("Legacy SCORM package detected")
                    else:
                        self.errors.append("Required manifest file not found (imsmanifest.xml or tincan.xml required)")
                
                # Check for common SCORM structure
                html_files = [f for f in file_list if f.lower().endswith(('.html', '.htm'))]
                if not html_files:
                    self.warnings.append("No HTML files found - this may not be a playable SCORM package")
                
                self.info.append(f"Files in package: {len(file_list)}")
                self.info.append(f"HTML files found: {len(html_files)}")
                
                return file_list
                
        except zipfile.BadZipFile:
            self.errors.append("Invalid ZIP file format")
            return []
        except Exception as e:
            self.errors.append(f"Error reading ZIP file: {str(e)}")
            return []
    
    def _validate_manifest(self, file_buffer, file_list) -> Optional[Dict]:
        """Validate imsmanifest.xml or tincan.xml structure and content"""
        manifest_file = None
        manifest_data = {}
        
        # Find manifest file (either imsmanifest.xml or tincan.xml)
        for file_name in file_list:
            if file_name.lower().endswith('imsmanifest.xml'):
                manifest_file = file_name
                manifest_data['type'] = 'scorm'
                break
            elif file_name.lower().endswith('tincan.xml'):
                manifest_file = file_name
                manifest_data['type'] = 'xapi'
                break
        
        if not manifest_file:
            self.errors.append("No manifest file found (imsmanifest.xml or tincan.xml required)")
            return None
        
        try:
            with zipfile.ZipFile(file_buffer, 'r') as zip_ref:
                manifest_content = zip_ref.read(manifest_file)
                
                # Parse XML
                try:
                    root = ET.fromstring(manifest_content)
                    manifest_data['parsed'] = True
                except ET.ParseError as e:
                    self.errors.append(f"Invalid manifest XML: {str(e)}")
                    return manifest_data
                
                # Handle different manifest types
                if manifest_data['type'] == 'xapi':
                    # For xAPI/Tin Can packages
                    manifest_data['version'] = 'xapi'
                    self.info.append("xAPI/Tin Can package detected")
                    self._validate_tincan_structure(root)
                else:
                    # For SCORM packages
                    version = self._detect_scorm_version(root)
                    manifest_data['version'] = version
                    self.info.append(f"SCORM version detected: {version}")
                    
                    # Validate basic structure
                    self._validate_manifest_structure(root, version)
                
                # Extract metadata
                manifest_data.update(self._extract_manifest_metadata(root))
                
                return manifest_data
                
        except Exception as e:
            self.errors.append(f"Error parsing manifest: {str(e)}")
            return manifest_data
    
    def _detect_scorm_version(self, root) -> str:
        """Detect SCORM version from manifest"""
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
    
    def _validate_tincan_structure(self, root):
        """Validate tincan.xml structure for xAPI packages"""
        try:
            # Check for tincan root element
            if not root.tag.lower().endswith('tincan'):
                self.errors.append("Invalid tincan.xml: root element should be <tincan>")
                return
            
            # Look for activities (they should be under <activities> element)
            activities_container = root.find('.//activities')
            if activities_container is None:
                self.errors.append("No <activities> element found in tincan.xml")
                return
            
            activities = activities_container.findall('.//activity')
            if not activities:
                self.errors.append("No activities found in tincan.xml")
                return
            
            # Validate first activity
            main_activity = activities[0]
            
            # Check for activity ID
            activity_id = main_activity.get('id')
            if not activity_id:
                self.warnings.append("Activity missing ID attribute")
            
            # Check for activity name
            name_elem = main_activity.find('.//name')
            if name_elem is None:
                self.warnings.append("Activity missing name element")
            else:
                langstring = name_elem.find('.//langstring')
                if langstring is None or not langstring.text:
                    self.warnings.append("Activity name missing langstring content")
            
            # Check for launch URL or entry point
            # For xAPI, this might be in extensions or other elements
            has_launch_info = False
            extensions = main_activity.find('.//extensions')
            if extensions is not None:
                has_launch_info = True
            
            # Also check for common entry points in the package
            # This will be validated during file extraction
            
            if not has_launch_info:
                self.warnings.append("No launch information found in tincan.xml - will use common entry points")
            
            self.info.append(f"Validated {len(activities)} activities in tincan.xml")
            
        except Exception as e:
            self.errors.append(f"Error validating tincan.xml structure: {str(e)}")
    
    def _validate_manifest_structure(self, root, version):
        """Validate manifest XML structure"""
        # Check for organizations
        organizations = root.find('.//organizations')
        if organizations is None:
            self.errors.append("Missing <organizations> element in manifest")
        else:
            # Check for organization
            org = organizations.find('.//organization')
            if org is None:
                self.errors.append("Missing <organization> element in manifest")
            else:
                # Check for items
                items = org.findall('.//item')
                if not items:
                    self.warnings.append("No <item> elements found in organization")
                else:
                    self.info.append(f"Course items found: {len(items)}")
        
        # Check for resources
        resources = root.find('.//resources')
        if resources is None:
            self.errors.append("Missing <resources> element in manifest")
        else:
            resource_list = resources.findall('.//resource')
            if not resource_list:
                self.errors.append("No <resource> elements found")
            else:
                self.info.append(f"Resources found: {len(resource_list)}")
                
                # Check for SCO resources
                sco_resources = [r for r in resource_list if r.get('type') == 'webcontent']
                if not sco_resources:
                    self.warnings.append("No webcontent resources found - may not be launchable")
    
    def _extract_manifest_metadata(self, root) -> Dict:
        """Extract useful metadata from manifest"""
        metadata = {}
        
        # Get package identifier
        metadata['identifier'] = root.get('identifier', '')
        
        # Get title from metadata or organization
        title = None
        
        # Try metadata first
        meta_elem = root.find('.//metadata')
        if meta_elem is not None:
            general = meta_elem.find('.//general')
            if general is not None:
                title_elem = general.find('.//title')
                if title_elem is not None:
                    langstring = title_elem.find('.//langstring')
                    if langstring is not None and langstring.text:
                        title = langstring.text.strip()
        
        # Try organization title
        if not title:
            org = root.find('.//organization')
            if org is not None:
                title_elem = org.find('.//title')
                if title_elem is not None and title_elem.text:
                    title = title_elem.text.strip()
        
        metadata['title'] = title or 'Untitled SCORM Package'
        
        return metadata
    
    def _validate_security(self, file_list):
        """Perform security validation on file list"""
        suspicious_files = []
        
        for file_path in file_list:
            filename = os.path.basename(file_path).lower()
            
            # Check for suspicious extensions
            for ext in self.SUSPICIOUS_EXTENSIONS:
                if filename.endswith(ext):
                    suspicious_files.append(file_path)
                    break
        
        if suspicious_files:
            self.warnings.append(f"Suspicious files detected: {', '.join(suspicious_files[:5])}")
            if len(suspicious_files) > 5:
                self.warnings.append(f"... and {len(suspicious_files) - 5} more suspicious files")
        
        # Check for directory traversal attempts
        dangerous_paths = [f for f in file_list if '..' in f or f.startswith('/')]
        if dangerous_paths:
            self.errors.append(f"Dangerous file paths detected: {', '.join(dangerous_paths[:3])}")
    
    def _validate_performance(self, file_list, file_buffer):
        """Validate package for performance issues"""
        large_files = []
        
        try:
            with zipfile.ZipFile(file_buffer, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    # Check for very large files (>50MB)
                    if file_info.file_size > 50 * 1024 * 1024:
                        large_files.append(f"{file_info.filename} ({file_info.file_size / (1024*1024):.1f}MB)")
        except Exception:
            pass  # Skip performance checks if ZIP can't be read
        
        if large_files:
            self.warnings.append(f"Large files detected: {', '.join(large_files[:3])}")
            if len(large_files) > 3:
                self.warnings.append(f"... and {len(large_files) - 3} more large files")


def validate_scorm_package(uploaded_file) -> Dict:
    """
    Convenience function to validate a SCORM package
    
    Args:
        uploaded_file: Django UploadedFile object
        
    Returns:
        dict: Validation results
    """
    validator = ScormPackageValidator()
    return validator.validate_package(uploaded_file)


def get_validation_summary(validation_results) -> str:
    """
    Get a human-readable summary of validation results
    
    Args:
        validation_results: Results from validate_scorm_package()
        
    Returns:
        str: Summary message
    """
    if not validation_results['valid']:
        return f" Invalid SCORM package ({len(validation_results['errors'])} errors)"
    elif validation_results['warnings']:
        return f" Valid with warnings ({len(validation_results['warnings'])} warnings)"
    else:
        return " Valid SCORM package"
