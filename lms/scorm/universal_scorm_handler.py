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
    
    # ENHANCED SCORM launch file patterns
    # PRIORITY ORDER: Check actual content files BEFORE wrapper/driver files
    LAUNCH_FILE_PATTERNS = [
        # PRIORITY 1: Direct content in scormcontent directory (actual content, not wrapper)
        'scormcontent/index.html',
        'scormcontent/story.html',
        'scormcontent/player.html',
        'scormcontent/presentation.html',
        'scormcontent/course.html',
        
        # PRIORITY 2: Direct Articulate Rise/Storyline content
        'story.html',
        'story_html5.html',
        'player.html',
        'rise/index.html',
        'storyline/index.html',
        'storyline/story.html',
        'storyline/story_html5.html',
        
        # PRIORITY 3: Adobe Captivate content
        'captivate/index.html',
        'captivate.html',
        'multiscreen.html',
        
        # PRIORITY 4: HTML5 packages
        'html5/index.html',
        'html5/story.html',
        'html5/player.html',
        'html5/content/index.html',
        
        # PRIORITY 5: Common content directories
        'content/index.html',
        'content/player.html',
        'content/story.html',
        'data/index.html',
        'data/player.html',
        
        # PRIORITY 6: Generic SCORM packages
        'index.html',
        'launch.html',
        'start.html',
        'main.html',
        'default.html',
        'player.html',
        'presentation.html',
        'course.html',
        'module.html',
        
        # PRIORITY 7: Lectora content
        'lectora/index.html',
        'lectora.html',
        
        # PRIORITY 8 (LAST): Articulate driver/wrapper (only if no direct content found)
        # These are just wrappers that load the actual content - avoid if possible
        'scormdriver/indexAPI.html',
        'scormdriver/index.html',
        'scormdriver/scormdriver.html',
    ]
    
    # ENHANCED Relative path patterns that need fixing
    RELATIVE_PATH_PATTERNS = [
        # Common relative paths
        '../scormcontent/',
        '../scormdriver/',
        '../story.html',
        '../index.html',
        '../html5/',
        '../content/',
        '../data/',
        '../rise/',
        '../storyline/',
        '../captivate/',
        '../lectora/',
        '../player.html',
        '../presentation.html',
        '../course.html',
        '../module.html',
        '../assets/',
        '../images/',
        '../js/',
        '../css/',
        '../media/',
        '../resources/',
        '../lib/',
        
        # Direct paths
        'scormcontent/',
        'scormdriver/',
        'story.html',
        'index.html',
        'html5/',
        'content/',
        'data/',
        'rise/',
        'storyline/',
        'captivate/',
        'lectora/',
        'player.html',
        'presentation.html',
        'course.html',
        'module.html',
        'assets/',
        'images/',
        'js/',
        'css/',
        'media/',
        'resources/',
        'lib/',
    ]
    
    @classmethod
    def detect_launch_file(cls, package_files: List[str]) -> Optional[str]:
        """
        ENHANCED: Robustly detect the correct launch file from package contents
        with improved heuristics and fallback mechanisms
        
        Args:
            package_files: List of files in the SCORM package
            
        Returns:
            The detected launch file path or None if not found
        """
        if not package_files:
            logger.warning("Empty package files list provided")
            return None
            
        # Convert to lowercase for case-insensitive matching
        files_lower = [f.lower() for f in package_files]
        
        # Score-based detection system
        launch_candidates = []
        
        # 1. Check exact matches with our patterns (highest priority)
        for pattern in cls.LAUNCH_FILE_PATTERNS:
            pattern_lower = pattern.lower()
            
            # Direct match
            if pattern_lower in files_lower:
                # Find the original case version
                for file in package_files:
                    if file.lower() == pattern_lower:
                        # Calculate pattern priority score (earlier patterns = higher priority)
                        pattern_index = cls.LAUNCH_FILE_PATTERNS.index(pattern)
                        priority_score = 1000 - pattern_index  # Higher score = higher priority
                        
                        launch_candidates.append((file, priority_score, "exact_match"))
                        logger.info(f"Exact launch file match: {file} (score: {priority_score})")
        
        # 2. Check for partial matches in directories
        for pattern in cls.LAUNCH_FILE_PATTERNS:
            if '/' in pattern:
                dir_part = pattern.split('/')[0]
                file_part = pattern.split('/')[-1]
                
                # Look for matching directory with matching file
                matching_files = []
                for file in package_files:
                    file_lower = file.lower()
                    if (file_lower.startswith(dir_part.lower() + '/') and 
                        file_lower.endswith(('.html', '.htm'))):
                        
                        # Exact filename match in directory gets higher score
                        if file_lower.endswith('/' + file_part.lower()):
                            pattern_index = cls.LAUNCH_FILE_PATTERNS.index(pattern)
                            score = 900 - pattern_index
                            matching_files.append((file, score, "dir_exact_match"))
                        else:
                            # Any HTML in the right directory gets medium score
                            pattern_index = cls.LAUNCH_FILE_PATTERNS.index(pattern)
                            score = 800 - pattern_index
                            matching_files.append((file, score, "dir_html_match"))
                
                # Sort by score and add best match
                if matching_files:
                    matching_files.sort(key=lambda x: x[1], reverse=True)
                    best_match = matching_files[0]
                    launch_candidates.append(best_match)
                    logger.info(f"Directory match: {best_match[0]} (score: {best_match[1]}, type: {best_match[2]})")
        
        # 3. Heuristic-based detection for common patterns
        for file in package_files:
            file_lower = file.lower()
            
            # Prioritize index.html files in root or common directories
            if file_lower == 'index.html' or file_lower.endswith('/index.html'):
                score = 700
                launch_candidates.append((file, score, "index_heuristic"))
                logger.info(f"Index heuristic match: {file} (score: {score})")
                
            # Prioritize story.html files (Articulate)
            elif file_lower == 'story.html' or file_lower.endswith('/story.html'):
                score = 650
                launch_candidates.append((file, score, "story_heuristic"))
                logger.info(f"Story heuristic match: {file} (score: {score})")
                
            # Check for imsmanifest.xml references
            elif file_lower.endswith('imsmanifest.xml'):
                # TODO: Parse manifest to find resource href if needed
                pass
        
        # 4. Fallback: Any HTML file (lowest priority)
        if not launch_candidates:
            html_files = [(file, 100, "fallback_html") for file in package_files 
                         if file.lower().endswith(('.html', '.htm'))]
            
            if html_files:
                # Prefer shorter paths and index/story files
                for i, (file, score, match_type) in enumerate(html_files):
                    file_lower = file.lower()
                    # Boost score for index/story files
                    if 'index.html' in file_lower:
                        html_files[i] = (file, score + 50, match_type)
                    elif 'story.html' in file_lower:
                        html_files[i] = (file, score + 40, match_type)
                    # Penalize long paths and scormdriver files
                    if file_lower.count('/') > 2:
                        html_files[i] = (file, score - 10 * file_lower.count('/'), match_type)
                    if 'scormdriver' in file_lower:
                        html_files[i] = (file, score - 30, match_type)
                
                # Sort by adjusted score
                html_files.sort(key=lambda x: x[1], reverse=True)
                if html_files:
                    launch_candidates.append(html_files[0])
                    logger.info(f"Fallback HTML match: {html_files[0][0]} (score: {html_files[0][1]})")
        
        # Select the best candidate
        if launch_candidates:
            # Sort by score (highest first)
            launch_candidates.sort(key=lambda x: x[1], reverse=True)
            best_candidate = launch_candidates[0]
            logger.info(f"✅ Selected launch file: {best_candidate[0]} (score: {best_candidate[1]}, type: {best_candidate[2]})")
            return best_candidate[0]
        
        logger.warning("❌ No launch file detected in package")
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
