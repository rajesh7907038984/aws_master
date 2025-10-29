"""
SCORM package processing utilities
"""
import zipfile
import xml.etree.ElementTree as ET
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def find_manifest_in_zip(zip_path) -> Optional[str]:
    """
    Find imsmanifest.xml in ZIP file
    
    Returns: Path to manifest file within ZIP
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            names = z.namelist()
            
            # Look for imsmanifest.xml (case-insensitive)
            possible = [n for n in names if n.lower().endswith('imsmanifest.xml')]
            
            if not possible:
                # Try to find in common locations
                for name in names:
                    if 'manifest' in name.lower() and name.lower().endswith('.xml'):
                        possible.append(name)
            
            if not possible:
                raise ValueError("No imsmanifest.xml found in ZIP")
            
            # Prefer root-level manifest
            root_manifests = [p for p in possible if p.count('/') <= 1]
            if root_manifests:
                return root_manifests[0]
            
            return possible[0]
    except Exception as e:
        logger.error(f"Error finding manifest in ZIP {zip_path}: {e}")
        raise


def parse_imsmanifest(zip_path, manifest_path=None) -> Dict:
    """
    Parse imsmanifest.xml and extract SCORM metadata
    
    Returns: Dictionary with manifest data
    """
    if manifest_path is None:
        manifest_path = find_manifest_in_zip(zip_path)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            with z.open(manifest_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Parse namespaces (SCORM uses ADL namespaces)
                namespaces = {
                    'default': root.tag.split('}')[0].strip('{') if '}' in root.tag else '',
                    'ims': 'http://www.imsproject.org/xsd/imscp_rootv1p1p2',
                    'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2',
                    'adlseq': 'http://www.adlnet.org/xsd/adlseq_v1p3',
                    'adlnav': 'http://www.adlnet.org/xsd/adlnav_v1p3',
                    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
                }
                
                # Clean up namespaces if they're in the tag
                for prefix, uri in list(namespaces.items()):
                    if '}' in root.tag:
                        # Try to auto-detect namespace
                        tag_ns = root.tag.split('}')[0].strip('{')
                        if tag_ns:
                            namespaces['default'] = tag_ns
                
                result = {
                    'organizations': [],
                    'resources': [],
                    'metadata': {},
                    'version': None
                }
                
                # Detect SCORM version
                version = detect_scorm_version(root, namespaces)
                result['version'] = version
                
                # Parse metadata
                metadata_elem = root.find('.//metadata', namespaces)
                if metadata_elem is not None:
                    schema_elem = metadata_elem.find('.//schema', namespaces)
                    if schema_elem is not None:
                        result['metadata']['schema'] = schema_elem.text
                    
                    schemaversion_elem = metadata_elem.find('.//schemaversion', namespaces)
                    if schemaversion_elem is not None:
                        result['metadata']['schemaversion'] = schemaversion_elem.text
                    
                    # Title
                    title_elem = metadata_elem.find('.//title', namespaces)
                    if title_elem is None:
                        title_elem = metadata_elem.find('.//{*}title')  # Try without namespace
                    if title_elem is not None:
                        result['metadata']['title'] = title_elem.text
                
                # Parse organizations
                orgs_elem = root.find('.//organizations', namespaces)
                if orgs_elem is None:
                    # Try without namespace prefix
                    orgs_elem = root.find('.//organizations')
                
                if orgs_elem is not None:
                    for org in orgs_elem.findall('.//organization', namespaces) or []:
                        org_data = {
                            'identifier': org.get('identifier', ''),
                            'title': '',
                            'items': []
                        }
                        
                        # Get title
                        title_elem = org.find('.//title', namespaces)
                        if title_elem is None:
                            title_elem = org.find('.//{*}title')
                        if title_elem is not None:
                            org_data['title'] = title_elem.text or ''
                        
                        # Parse items
                        items_elem = org.find('.//item', namespaces)
                        if items_elem is None:
                            items_elem = org.find('.//{*}item')
                        
                        if items_elem is not None:
                            item_data = parse_item(items_elem, namespaces)
                            org_data['items'].append(item_data)
                        
                        result['organizations'].append(org_data)
                
                # Parse resources
                resources_elem = root.find('.//resources', namespaces)
                if resources_elem is None:
                    resources_elem = root.find('.//{*}resources')
                
                if resources_elem is not None:
                    for resource in resources_elem.findall('.//resource', namespaces) or []:
                        resource_data = {
                            'identifier': resource.get('identifier', ''),
                            'type': resource.get('type', ''),
                            'href': resource.get('href', ''),
                            'base': resource.get('base', ''),
                        }
                        
                        # Get title if available
                        title_elem = resource.find('.//title', namespaces)
                        if title_elem is None:
                            title_elem = resource.find('.//{*}title')
                        if title_elem is not None:
                            resource_data['title'] = title_elem.text
                        
                        result['resources'].append(resource_data)
                
                return result
                
    except Exception as e:
        logger.error(f"Error parsing manifest {manifest_path}: {e}")
        raise


def parse_item(item_elem, namespaces):
    """Parse an item element from manifest"""
    item_data = {
        'identifier': item_elem.get('identifier', ''),
        'identifierref': item_elem.get('identifierref', ''),
        'title': '',
        'items': []
    }
    
    # Get title
    title_elem = item_elem.find('.//title', namespaces)
    if title_elem is None:
        title_elem = item_elem.find('.//{*}title')
    if title_elem is not None:
        item_data['title'] = title_elem.text or ''
    
    # Recursively parse child items
    for child_item in item_elem.findall('.//item', namespaces) or []:
        child_data = parse_item(child_item, namespaces)
        item_data['items'].append(child_data)
    
    return item_data


def detect_scorm_version(root, namespaces) -> Optional[str]:
    """
    Detect SCORM version from manifest root
    """
    # Check metadata/schema for SCORM version indicators
    metadata_elem = root.find('.//metadata', namespaces)
    if metadata_elem is not None:
        schema_elem = metadata_elem.find('.//schema', namespaces)
        if schema_elem is not None:
            schema_text = schema_elem.text or ''
            if '2004' in schema_text or 'CAM' in schema_text:
                return '2004'
            elif '1.2' in schema_text or 'CP' in schema_text:
                return '1.2'
        
        schemaversion_elem = metadata_elem.find('.//schemaversion', namespaces)
        if schemaversion_elem is not None:
            version_text = schemaversion_elem.text or ''
            if '2004' in version_text or '4' in version_text:
                return '2004'
            elif '1.2' in version_text:
                return '1.2'
    
    # Check for ADL namespaces that indicate SCORM 2004
    if any('2004' in ns or 'adlseq' in ns.lower() or 'adlnav' in ns.lower() 
           for ns in namespaces.values()):
        return '2004'
    
    # Default to 1.2 if can't determine
    return '1.2'


def parse_scorm_time(time_str: str, version: str) -> float:
    """
    Normalize SCORM time formats to total seconds (float)
    
    Args:
        time_str: Time string from SCORM (HH:MM:SS.SS or PT#H#M#S format)
        version: SCORM version ('1.2' or '2004')
    
    Returns:
        Total seconds as float
    """
    if not time_str:
        return 0.0
    
    try:
        if version == "1.2":
            # Format: HH:MM:SS.SS or HH:MM:SS
            parts = time_str.split(":")
            if len(parts) < 3:
                return 0.0
            
            h = int(parts[0]) if parts[0] else 0
            m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            s = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
            
            return h * 3600 + m * 60 + s
            
        elif version == "2004" and time_str.startswith("PT"):
            # Format: PT#H#M#S (ISO8601 duration)
            h = 0
            m = 0
            s = 0.0
            
            if 'H' in time_str:
                h_match = re.search(r'(\d+)H', time_str)
                if h_match:
                    h = int(h_match.group(1))
            
            if 'M' in time_str:
                m_match = re.search(r'(\d+)M', time_str)
                if m_match:
                    m = int(m_match.group(1))
            
            if 'S' in time_str:
                s_match = re.search(r'(\d+(?:\.\d+)?)S', time_str)
                if s_match:
                    s = float(s_match.group(1))
            
            return h * 3600 + m * 60 + s
        
        return 0.0
    except (ValueError, AttributeError, IndexError) as e:
        logger.warning(f"Error parsing SCORM time '{time_str}': {e}")
        return 0.0


def validate_zip_file(zip_path, max_size_mb=600, max_files=10000):
    """
    Validate ZIP file before extraction
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check file size
        file_size = Path(zip_path).stat().st_size
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size > max_size_bytes:
            return False, f"ZIP file exceeds maximum size of {max_size_mb}MB"
        
        # Check ZIP structure
        with zipfile.ZipFile(zip_path, 'r') as z:
            file_list = z.namelist()
            
            # Check file count
            if len(file_list) > max_files:
                return False, f"ZIP contains more than {max_files} files"
            
            # Check for dangerous paths
            dangerous_patterns = ['../', '/etc/', '/windows/', '/system32/']
            executable_extensions = ['.exe', '.bat', '.cmd', '.sh', '.php', '.jsp', '.asp']
            
            for file_name in file_list:
                # Check for path traversal
                if any(pattern in file_name for pattern in dangerous_patterns):
                    return False, f"Invalid path detected: {file_name}"
                
                # Check for absolute paths
                if file_name.startswith('/') or (len(file_name) > 1 and file_name[1] == ':'):
                    return False, f"Absolute path not allowed: {file_name}"
                
                # Check for executables
                file_lower = file_name.lower()
                if any(file_lower.endswith(ext) for ext in executable_extensions):
                    return False, f"Executable file type not allowed: {file_name}"
        
        return True, None
        
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file format"
    except Exception as e:
        logger.error(f"Error validating ZIP file: {e}")
        return False, f"Validation error: {str(e)}"

