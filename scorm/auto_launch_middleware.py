"""
Middleware to automatically detect and fix SCORM launch URLs
"""

import logging
from django.http import HttpResponse
from scorm.auto_launch_detector import launch_detector

logger = logging.getLogger(__name__)

class ScormAutoLaunchMiddleware:
    """
    Middleware to automatically detect and fix SCORM launch URLs
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is a SCORM content request
        if request.path.startswith('/scorm/content/'):
            try:
                # Extract topic ID from path
                path_parts = request.path.split('/')
                if len(path_parts) >= 4 and path_parts[2] == 'content':
                    topic_id = path_parts[3]
                    
                    # Get the SCORM package for this topic
                    from courses.models import Topic
                    from scorm.models import ScormPackage
                    
                    try:
                        topic = Topic.objects.get(id=topic_id)
                        if hasattr(topic, 'scorm_package'):
                            scorm_package = topic.scorm_package
                            
                            # Check if launch URL needs fixing
                            if self.needs_launch_url_fix(scorm_package):
                                logger.info(f"Auto-fixing launch URL for topic {topic_id}")
                                launch_file, message = launch_detector.auto_detect_launch_url(scorm_package)
                                
                                if launch_file:
                                    logger.info(f"Auto-detected launch URL: {launch_file}")
                                else:
                                    logger.warning(f"Could not auto-detect launch URL: {message}")
                                    
                    except Topic.DoesNotExist:
                        pass
                    except Exception as e:
                        logger.error(f"Error in auto-launch middleware: {str(e)}")
                        
        response = self.get_response(request)
        return response
    
    def needs_launch_url_fix(self, scorm_package):
        """
        Check if a SCORM package needs its launch URL fixed
        """
        # Check if current launch URL is problematic
        problematic_patterns = [
            'scormcontent/index.html',  # Old pattern
            'index.html',  # Too generic
            '',  # Empty
            None  # None
        ]
        
        current_launch = scorm_package.launch_url
        
        # If it's one of the problematic patterns, try to fix it
        if current_launch in problematic_patterns:
            return True
        
        # Check if the file actually exists
        try:
            files = launch_detector.list_package_files(scorm_package)
            if current_launch not in files:
                return True
        except:
            return True
        
        return False
