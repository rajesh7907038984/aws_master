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
                # Read raw XML first to extract namespaces (ElementTree doesn't expose xmlns: attributes)
                manifest_xml = f.read().decode('utf-8')
            
            # Extract namespace declarations from raw XML using regex
            # This is critical for correct version detection
            import re
            namespaces = {}
            
            # Extract default namespace from xmlns="..."
            default_ns_match = re.search(r'<manifest[^>]*xmlns="([^"]+)"', manifest_xml)
            if default_ns_match:
                namespaces['default'] = default_ns_match.group(1)
            
            # Extract all xmlns:prefix="..." declarations
            xmlns_pattern = r'xmlns:(\w+)="([^"]+)"'
            for match in re.finditer(xmlns_pattern, manifest_xml[:3000]):  # Check first 3000 chars
                prefix = match.group(1)
                uri = match.group(2)
                namespaces[prefix] = uri
            
            # Add helper mappings for XPath queries
            if 'default' in namespaces:
                default_uri = namespaces['default']
                # Map default to specific known types for easier XPath queries
                if 'imscp_v1p1' in default_uri or 'imsglobal' in default_uri:
                    namespaces['ims'] = default_uri
                    namespaces['ims1p1'] = default_uri
                elif 'imscp_rootv1p1p2' in default_uri or 'imsproject' in default_uri:
                    namespaces['ims'] = default_uri
                    namespaces['ims1p2'] = default_uri
            
            # Now parse the XML with ElementTree
            root = ET.fromstring(manifest_xml)
            
            result = {
                'organizations': [],
                'resources': [],
                'metadata': {},
                'version': None
            }
            
            # Detect SCORM version
            version = detect_scorm_version(root, namespaces)
            result['version'] = version
            
            # Get default namespace for XPath queries
            default_ns = namespaces.get('default', '')
            
            # Parse metadata - find by iterating (Python 3.7 compatible)
            metadata_elem = None
            for elem in root.iter():
                if elem.tag.endswith('metadata'):
                    metadata_elem = elem
                    break
            
            if metadata_elem is not None:
                for child in metadata_elem.iter():
                    if child.tag.endswith('schema') and child.text:
                        result['metadata']['schema'] = child.text
                    elif child.tag.endswith('schemaversion') and child.text:
                        result['metadata']['schemaversion'] = child.text
                    elif child.tag.endswith('title') and child.text:
                        result['metadata']['title'] = child.text
            
            # Parse organizations - find by iterating through root children
            orgs_elem = None
            for child in root:
                if child.tag.endswith('organizations'):
                    orgs_elem = child
                    break
            
            if orgs_elem is not None:
                # Find direct children organization elements
                orgs = [child for child in orgs_elem if child.tag.endswith('organization')]
                
                for org in orgs:
                    org_data = {
                        'identifier': org.get('identifier', ''),
                        'title': '',
                        'items': []
                    }
                    
                    # Get title - find by iterating
                    for elem in org.iter():
                        if elem.tag.endswith('title') and elem.text:
                            org_data['title'] = elem.text
                            break
                    
                    # Parse items - find direct children only
                    items = [item for item in org if item.tag.endswith('item')]
                    for item_elem in items:
                        item_data = parse_item(item_elem, namespaces, default_ns)
                        org_data['items'].append(item_data)
                    
                    result['organizations'].append(org_data)
            
            # Parse resources - find by iterating through root children
            resources_elem = None
            for child in root:
                if child.tag.endswith('resources'):
                    resources_elem = child
                    break
            
            if resources_elem is not None:
                # Find direct children resource elements
                resources = [child for child in resources_elem if child.tag.endswith('resource')]
                
                for resource in resources:
                    resource_data = {
                        'identifier': resource.get('identifier', ''),
                        'type': resource.get('type', ''),
                        'href': resource.get('href', ''),
                        'base': resource.get('base', ''),
                    }
                    
                    # Extract SCORM-specific attributes (adlcp:scormType)
                    scorm_type = None
                    
                    # Method 1: Try with known namespace prefixes
                    for ns_prefix in ['adlcp', 'adlcp1p3', 'adl']:
                        ns_uri = namespaces.get(ns_prefix, '')
                        if ns_uri:
                            scorm_type = resource.get(f'{{{ns_uri}}}scormType')
                            if scorm_type:
                                break
                    
                    # Method 2: Try without namespace
                    if not scorm_type:
                        scorm_type = resource.get('scormType')
                    
                    # Method 3: Check all attributes for scormtype pattern
                    if not scorm_type:
                        for attr_name, attr_value in resource.attrib.items():
                            if 'scormtype' in attr_name.lower() or attr_name.endswith('scormType'):
                                scorm_type = attr_value
                                break
                    
                    if scorm_type:
                        resource_data['scormType'] = scorm_type
                    
                    # Get title if available - find by iterating
                    for elem in resource.iter():
                        if elem.tag.endswith('title') and elem.text:
                            resource_data['title'] = elem.text
                            break
                    
                    result['resources'].append(resource_data)
            
            return result
                
    except Exception as e:
        logger.error(f"Error parsing manifest {manifest_path}: {e}")
        raise


def parse_item(item_elem, namespaces, default_ns=None):
    """Parse an item element from manifest - Python 3.7 compatible"""
    item_data = {
        'identifier': item_elem.get('identifier', ''),
        'identifierref': item_elem.get('identifierref', ''),
        'title': '',
        'items': []
    }
    
    # Get title - find by iterating
    for elem in item_elem.iter():
        if elem.tag.endswith('title') and elem.text:
            item_data['title'] = elem.text
            break
    
    # Recursively parse child items - find direct children only
    child_items = [child for child in item_elem if child.tag.endswith('item')]
    for child_item in child_items:
        child_data = parse_item(child_item, namespaces, default_ns)
        item_data['items'].append(child_data)
    
    return item_data


def detect_scorm_version(root, namespaces) -> Optional[str]:
    """
    Detect SCORM version from manifest root - Python 3.7 compatible
    
    Priority order:
    1. schemaversion element (most reliable)
    2. schema element 
    3. ADL namespaces
    4. Default to 1.2
    """
    # Find metadata element by iterating
    metadata_elem = None
    for elem in root.iter():
        if elem.tag.endswith('metadata'):
            metadata_elem = elem
            break
    
    if metadata_elem is not None:
        # PRIORITY 1: Check schemaversion first (most explicit)
        schemaversion_text = None
        schema_text = None
        
        for elem in metadata_elem.iter():
            if elem.tag.endswith('schemaversion') and elem.text:
                schemaversion_text = elem.text.strip()
            elif elem.tag.endswith('schema') and elem.text:
                schema_text = elem.text.strip()
        
        if schemaversion_text:
            # Be explicit with version checks to avoid false matches
            if schemaversion_text == '1.2':
                return '1.2'
            elif schemaversion_text in ['2004', '2004 3rd Edition', '2004 4th Edition', 'CAM 1.3']:
                return '2004'
            # Check for partial matches
            elif '1.2' in schemaversion_text:
                return '1.2'
            elif '2004' in schemaversion_text:
                return '2004'
        
        # PRIORITY 2: Check schema element
        if schema_text:
            if '2004' in schema_text or 'CAM' in schema_text:
                return '2004'
            elif '1.2' in schema_text or 'CP' in schema_text:
                return '1.2'
    
    # PRIORITY 3: Check for ADL namespaces that indicate SCORM 2004
    # Only trust namespaces if metadata didn't give us an answer
    if any('2004' in ns or 'adlseq' in ns.lower() or 'adlnav' in ns.lower() 
           for ns in namespaces.values()):
        return '2004'
    
    # Check for SCORM 1.2 specific namespace
    if any('adlcp_rootv1p2' in ns or 'imscp_rootv1p1p2' in ns 
           for ns in namespaces.values()):
        return '1.2'
    
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


def validate_manifest_structure(zip_path, manifest_path=None) -> Tuple[bool, Optional[str]]:
    """
    Validate that manifest has required SCORM structure
    Handles both namespaced and non-namespaced manifests
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if manifest_path is None:
            manifest_path = find_manifest_in_zip(zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            with z.open(manifest_path) as f:
                try:
                    tree = ET.parse(f)
                    root = tree.getroot()
                except ET.ParseError as e:
                    return False, f"Invalid XML in manifest: {str(e)}"
                
                # Extract namespace if present
                namespace = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'ns': ''}
                
                # Helper function to find elements with or without namespace
                def find_element(tag_name):
                    # Try with wildcard namespace
                    elem = root.find(f'.//{{{namespace["ns"]}}}{tag_name}')
                    if elem is None:
                        # Try without namespace
                        elem = root.find(f'.//{tag_name}')
                    if elem is None:
                        # Try with any namespace using iteration
                        for elem in root.iter():
                            if elem.tag.endswith(tag_name) or elem.tag == tag_name:
                                return elem
                    return elem
                
                # Check for required elements
                orgs_elem = find_element('organizations')
                if orgs_elem is None:
                    return False, "Missing <organizations> element in manifest"
                
                resources_elem = find_element('resources')
                if resources_elem is None:
                    return False, "Missing <resources> element in manifest"
                
                # Check that at least one organization or resource exists
                # Some packages have empty organizations but valid resources
                org_count = len([e for e in root.iter() if e.tag.endswith('organization')])
                resource_count = len([e for e in root.iter() if e.tag.endswith('resource')])
                
                if org_count == 0 and resource_count == 0:
                    return False, "No <organization> or <resource> elements found in manifest"
                
                if resource_count == 0:
                    return False, "No <resource> elements found in manifest"
                
                return True, None
                
    except Exception as e:
        return False, f"Error validating manifest: {str(e)}"


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

