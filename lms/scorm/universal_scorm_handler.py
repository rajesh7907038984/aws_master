"""
Universal SCORM Package Handler
Automatically detects and handles all SCORM package types
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class UniversalSCORMHandler:
    """
    Universal handler for all SCORM package types
    Automatically detects launch files and handles URL resolution
    """
    
    # Common SCORM launch file patterns
    # PRIORITY ORDER: Check actual content files BEFORE wrapper/driver files
    LAUNCH_FILE_PATTERNS = [
        # PRIORITY 1: Direct content in scormcontent directory (actual content, not wrapper)
        'scormcontent/index.html',
        'scormcontent/story.html',
        
        # PRIORITY 2: Direct Articulate Rise/Storyline content
        'story.html',
        'story_html5.html',
        
        # PRIORITY 3: HTML5 packages
        'html5/index.html',
        'html5/story.html',
        
        # PRIORITY 4: Generic SCORM packages
        'index.html',
        'launch.html',
        'start.html',
        'main.html',
        'default.html',
        
        # PRIORITY 5 (LAST): Articulate driver/wrapper (only if no direct content found)
        # These are just wrappers that load the actual content - avoid if possible
        'scormdriver/indexAPI.html',
        'scormdriver/index.html',
    ]
    
    # Relative path patterns that need fixing
    RELATIVE_PATH_PATTERNS = [
        # Common relative paths
        '../scormcontent/',
        '../scormdriver/',
        '../story.html',
        '../index.html',
        '../html5/',
        
        # Direct paths
        'scormcontent/',
        'scormdriver/',
        'story.html',
        'index.html',
        'html5/',
    ]
    
    @classmethod
    def detect_launch_file(cls, package_files: List[str]) -> Optional[str]:
        """
        Automatically detect the correct launch file from package contents
        
        Args:
            package_files: List of files in the SCORM package
            
        Returns:
            The detected launch file path or None if not found
        """
        # Convert to lowercase for case-insensitive matching
        files_lower = [f.lower() for f in package_files]
        
        # Check patterns in order of preference
        for pattern in cls.LAUNCH_FILE_PATTERNS:
            pattern_lower = pattern.lower()
            
            # Direct match
            if pattern_lower in files_lower:
                # Find the original case version
                for file in package_files:
                    if file.lower() == pattern_lower:
                        logger.info(f"Detected launch file: {file}")
                        return file
            
            # Partial match for directories
            if '/' in pattern:
                dir_part = pattern.split('/')[0]
                if any(f.startswith(dir_part.lower() + '/') for f in files_lower):
                    # Look for index files in this directory
                    for file in package_files:
                        if file.lower().startswith(dir_part.lower() + '/') and file.lower().endswith(('.html', '.htm')):
                            logger.info(f"Detected launch file in directory: {file}")
                            return file
        
        # Fallback: look for any HTML file
        for file in package_files:
            if file.lower().endswith(('.html', '.htm')):
                logger.info(f"Fallback launch file detected: {file}")
                return file
        
        logger.warning("No launch file detected in package")
        return None
    
    @classmethod
    def fix_relative_paths(cls, html_content: str, topic_id: int) -> str:
        """
        Fix relative paths in SCORM content to use absolute URLs
        
        Args:
            html_content: The HTML content to fix
            topic_id: The topic ID for URL generation
            
        Returns:
            HTML content with fixed paths
        """
        base_content_url = f"/scorm/content/{topic_id}"
        
        # Prevent double replacement
        if base_content_url in html_content:
            logger.info(f"Content already has absolute paths for topic {topic_id}")
            return html_content
        
        # Special handling for scormdriver content location (do this first)
        if 'scormdriver' in html_content and 'strContentLocation' in html_content:
            html_content = cls._fix_scormdriver_content_location(html_content, base_content_url)
        
        # Fix other relative paths
        fixes_applied = 0
        for old_path in cls.RELATIVE_PATH_PATTERNS:
            if old_path in html_content:
                if old_path.startswith('../'):
                    new_path = f'{base_content_url}/{old_path[3:]}'  # Remove ../
                else:
                    new_path = f'{base_content_url}/{old_path}'
                
                # Only replace if not already replaced and not already contains base URL
                if new_path not in html_content and base_content_url not in old_path:
                    html_content = html_content.replace(old_path, new_path)
                    fixes_applied += 1
                    logger.info(f"Fixed relative path: {old_path} -> {new_path}")
        
        logger.info(f"Applied {fixes_applied} path fixes for topic {topic_id}")
        return html_content
    
    @classmethod
    def _fix_scormdriver_content_location(cls, html_content: str, base_content_url: str) -> str:
        """
        Fix scormdriver content location specifically
        
        Args:
            html_content: HTML content
            base_content_url: Base content URL
            
        Returns:
            Fixed HTML content
        """
        # Find and fix the content location dynamically
        content_location_pattern = r'strContentLocation\s*=\s*["\']([^"\']+)["\']'
        match = re.search(content_location_pattern, html_content)
        
        if match:
            original_location = match.group(1)
            
            # Only fix if it's a relative path and not already fixed
            if original_location.startswith('../') and base_content_url not in original_location:
                # Remove the ../ prefix and add base URL
                fixed_location = original_location.replace('../', f'{base_content_url}/')
                html_content = html_content.replace(
                    f'strContentLocation = "{original_location}"',
                    f'strContentLocation = "{fixed_location}"'
                )
                logger.info(f"Fixed scormdriver content location: {original_location} -> {fixed_location}")
            elif base_content_url in original_location:
                # Already fixed, but might have double paths - clean them up
                if f'{base_content_url}/{base_content_url}' in original_location:
                    cleaned_location = original_location.replace(f'{base_content_url}/{base_content_url}', base_content_url)
                    html_content = html_content.replace(
                        f'strContentLocation = "{original_location}"',
                        f'strContentLocation = "{cleaned_location}"'
                    )
                    logger.info(f"Cleaned double paths in content location: {original_location} -> {cleaned_location}")
        
        return html_content
    
    @classmethod
    def get_package_type(cls, launch_url: str) -> str:
        """
        Determine the SCORM package type based on launch URL
        
        Args:
            launch_url: The launch URL of the package
            
        Returns:
            Package type string
        """
        launch_lower = launch_url.lower()
        
        if 'scormdriver' in launch_lower:
            return 'storyline'
        elif 'story.html' in launch_lower:
            return 'rise'
        elif 'scormcontent' in launch_lower:
            return 'direct_content'
        elif 'html5' in launch_lower:
            return 'html5'
        else:
            return 'generic'
    
    @classmethod
    def validate_package_structure(cls, package_files: List[str], launch_url: str) -> Dict[str, bool]:
        """
        Validate that a SCORM package has the required structure
        
        Args:
            package_files: List of files in the package
            launch_url: The launch URL
            
        Returns:
            Dictionary with validation results
        """
        files_lower = [f.lower() for f in package_files]
        
        validation = {
            'has_manifest': any('manifest' in f for f in files_lower),
            'has_launch_file': launch_url.lower() in files_lower,
            'has_content': any('content' in f or 'story' in f for f in files_lower),
            'has_assets': any('asset' in f or 'css' in f or 'js' in f for f in files_lower),
        }
        
        validation['is_valid'] = all(validation.values())
        
        return validation
