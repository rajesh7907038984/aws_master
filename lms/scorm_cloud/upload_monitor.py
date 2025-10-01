
# SCORM Upload Monitor
# Monitors large file uploads and provides status updates

import time
import logging
from django.conf import settings

logger = logging.getLogger('scorm_upload_monitor')

def monitor_large_upload(file_size, estimated_time):
    """Monitor large file upload progress"""
    logger.info(f"Starting upload monitor for {file_size}MB file")
    logger.info(f"Estimated upload time: {estimated_time} minutes")
    
    # Log progress every 5 minutes
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > estimated_time * 60:
            logger.warning(f"Upload taking longer than expected: {elapsed/60:.1f} minutes")
        time.sleep(300)  # Check every 5 minutes
