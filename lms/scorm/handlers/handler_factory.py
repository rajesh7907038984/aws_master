"""
SCORM Handler Factory
Automatically selects the appropriate handler based on package type
"""
import logging
from .storyline_handler import StorylineHandler
from .rise360_handler import Rise360Handler
from .captivate_handler import CaptivateHandler
from .generic_handler import GenericHandler

logger = logging.getLogger(__name__)


def detect_package_type(scorm_package):
    """
    Detect SCORM package type from package metadata
    
    Returns:
        str: 'storyline', 'rise360', 'captivate', or 'generic'
    """
    try:
        launch_url = scorm_package.launch_url.lower() if scorm_package.launch_url else ''
        manifest_data = scorm_package.manifest_data or {}
        title = str(manifest_data.get('title', '')).lower()
        
        # Check for Articulate Storyline
        if 'story.html' in launch_url or 'story_html5.html' in launch_url:
            logger.info(f"📘 Detected Storyline package (launch_url: {launch_url})")
            return 'storyline'
        
        # Check for Articulate Rise 360
        if 'scormcontent/index.html' in launch_url or 'index.html#/lessons/' in launch_url:
            logger.info(f"📗 Detected Rise 360 package (launch_url: {launch_url})")
            return 'rise360'
        
        # Check manifest for Rise 360 markers
        if manifest_data:
            resources = manifest_data.get('resources', [])
            for resource in resources:
                if isinstance(resource, dict):
                    href = resource.get('href', '').lower()
                    if 'scormcontent' in href and 'lib/' in href:
                        logger.info(f"📗 Detected Rise 360 package (manifest structure)")
                        return 'rise360'
        
        # Check for Adobe Captivate
        if 'captivate' in launch_url or 'multiscreen.html' in launch_url:
            logger.info(f"🎬 Detected Captivate package (launch_url: {launch_url})")
            return 'captivate'
        
        if 'captivate' in title or 'adobe' in title:
            logger.info(f"🎬 Detected Captivate package (title: {title})")
            return 'captivate'
        
        # Default to generic
        logger.info(f"📦 Using generic SCORM handler (launch_url: {launch_url})")
        return 'generic'
        
    except Exception as e:
        logger.error(f"Error detecting package type: {str(e)}")
        return 'generic'


def get_handler_for_attempt(attempt):
    """
    Get the appropriate SCORM handler for an attempt
    
    Args:
        attempt: ScormAttempt instance
    
    Returns:
        BaseScormAPIHandler subclass instance
    """
    try:
        package_type = detect_package_type(attempt.scorm_package)
        
        # Select handler based on package type
        if package_type == 'storyline':
            handler = StorylineHandler(attempt)
            logger.info(f" Using StorylineHandler for attempt {attempt.id}")
        elif package_type == 'rise360':
            handler = Rise360Handler(attempt)
            logger.info(f" Using Rise360Handler for attempt {attempt.id}")
        elif package_type == 'captivate':
            handler = CaptivateHandler(attempt)
            logger.info(f" Using CaptivateHandler for attempt {attempt.id}")
        else:
            handler = GenericHandler(attempt)
            logger.info(f" Using GenericHandler for attempt {attempt.id}")
        
        return handler
        
    except Exception as e:
        logger.error(f"Error creating handler, falling back to GenericHandler: {str(e)}")
        return GenericHandler(attempt)

