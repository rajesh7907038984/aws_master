"""
SCORM Cloud utilities package.
"""

import logging

logger = logging.getLogger(__name__)

# Initialize SCORM Cloud API
try:
    from .api import SCORMCloudAPI, SCORMCloudError, get_scorm_client
    logger.info("SCORM Cloud API initialized")
except ImportError as e:
    logger.error(f"Failed to initialize SCORM Cloud API: {str(e)}")

# Initialize async uploader
try:
    from .async_uploader import enqueue_upload
    logger.info("SCORM Cloud async uploader initialized")
except ImportError as e:
    logger.warning(f"Failed to initialize SCORM async uploader: {str(e)}")
