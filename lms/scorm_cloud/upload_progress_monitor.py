
import time
import logging
from django.conf import settings
from scorm_cloud.utils.redis_fallback import get_robust_fallback

logger = logging.getLogger('scorm_upload_progress')

class LargeFileUploadMonitor:
    """Monitor large file uploads and provide progress updates"""
    
    def __init__(self, file_size_mb, topic_id):
        self.file_size_mb = file_size_mb
        self.topic_id = topic_id
        self.start_time = time.time()
        self.estimated_time = self._calculate_estimated_time()
        self.cache = get_robust_fallback()
        
    def _calculate_estimated_time(self):
        """Calculate estimated upload time based on file size"""
        # Base time: 2 minutes per 100MB
        base_time = (self.file_size_mb / 100) * 120
        
        # Add buffer for very large files
        if self.file_size_mb > 500:
            base_time *= 1.5  # 50% buffer for 500MB+ files
            
        return min(base_time, 14400)  # Cap at 4 hours
    
    def start_monitoring(self):
        """Start monitoring the upload"""
        logger.info(f"Starting upload monitor for {self.file_size_mb}MB file (Topic {self.topic_id})")
        logger.info(f"Estimated upload time: {self.estimated_time/60:.1f} minutes")
        
        # Store monitoring info in cache
        self.cache.set(
            f"scorm_upload_monitor_{self.topic_id}",
            {
                'file_size_mb': self.file_size_mb,
                'start_time': self.start_time,
                'estimated_time': self.estimated_time,
                'status': 'uploading'
            },
            timeout=14400  # 4 hours
        )
    
    def update_progress(self, progress_percent=None):
        """Update upload progress"""
        elapsed = time.time() - self.start_time
        
        if progress_percent:
            logger.info(f"Upload progress: {progress_percent}% (Topic {self.topic_id})")
        else:
            # Estimate progress based on elapsed time
            estimated_progress = min((elapsed / self.estimated_time) * 100, 95)
            logger.info(f"Upload progress: ~{estimated_progress:.1f}% (Topic {self.topic_id})")
        
        # Update cache
        self.cache.set(
            f"scorm_upload_monitor_{self.topic_id}",
            {
                'file_size_mb': self.file_size_mb,
                'start_time': self.start_time,
                'estimated_time': self.estimated_time,
                'status': 'uploading',
                'progress_percent': progress_percent or estimated_progress,
                'elapsed_time': elapsed
            },
            timeout=14400
        )
    
    def complete_upload(self, success=True):
        """Mark upload as complete"""
        elapsed = time.time() - self.start_time
        
        if success:
            logger.info(f"Upload completed successfully in {elapsed/60:.1f} minutes (Topic {self.topic_id})")
            status = 'completed'
        else:
            logger.error(f"Upload failed after {elapsed/60:.1f} minutes (Topic {self.topic_id})")
            status = 'failed'
        
        # Update cache
        self.cache.set(
            f"scorm_upload_monitor_{self.topic_id}",
            {
                'file_size_mb': self.file_size_mb,
                'start_time': self.start_time,
                'estimated_time': self.estimated_time,
                'status': status,
                'elapsed_time': elapsed,
                'completed_at': time.time()
            },
            timeout=14400
        )
    
    def get_status(self):
        """Get current upload status"""
        return self.cache.get(f"scorm_upload_monitor_{self.topic_id}")

def monitor_large_upload(file_size_mb, topic_id):
    """Create and start monitoring for a large upload"""
    monitor = LargeFileUploadMonitor(file_size_mb, topic_id)
    monitor.start_monitoring()
    return monitor
