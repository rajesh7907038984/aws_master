"""
Enhanced Temporary SCORM Storage System
Stores SCORM files temporarily in root folder and cleans up after launch URL creation
"""

import os
import uuid
import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

class TempSCORMStorage:
    """
    Temporary SCORM storage that:
    1. Stores files in root folder temporarily
    2. Automatically cleans up after launch URL is created
    3. Monitors and cleans orphaned files
    """
    
    def __init__(self):
        # Use project-relative path instead of hardcoded production path
        from django.conf import settings
        self.root_path = Path(settings.BASE_DIR) / 'scorm_temp'
        self.root_path.mkdir(exist_ok=True)
        self.active_uploads = {}  # Track active uploads
        self.lock = threading.Lock()
        self.start_cleanup_monitor()
    
    def get_temp_upload_path(self, filename):
        """
        Get temporary upload path for SCORM files in root folder
        """
        # Create unique filename to avoid conflicts
        name, ext = os.path.splitext(filename)
        unique_name = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
        
        temp_path = self.root_path / unique_name
        
        # Track this upload
        with self.lock:
            self.active_uploads[str(temp_path)] = {
                'created_at': datetime.now(),
                'status': 'uploading',
                'filename': filename
            }
        
        logger.info(f"Created temp upload path: {temp_path}")
        return str(temp_path)
    
    def save_uploaded_file(self, uploaded_file, temp_path):
        """
        Save uploaded file to temporary location
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            
            # Write file in chunks
            with open(temp_path, 'wb') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Update tracking
            with self.lock:
                if temp_path in self.active_uploads:
                    self.active_uploads[temp_path].update({
                        'status': 'ready',
                        'size': os.path.getsize(temp_path)
                    })
            
            logger.info(f"Saved SCORM file to temp location: {temp_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving uploaded file: {str(e)}")
            return False
    
    def cleanup_after_launch_url_created(self, temp_path):
        """
        Clean up temporary file after launch URL is successfully created
        """
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.info(f"Cleaned up temp file after launch URL creation: {temp_path}")
            
            # Remove from tracking
            with self.lock:
                self.active_uploads.pop(temp_path, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up temp file {temp_path}: {str(e)}")
            return False
    
    def cleanup_orphaned_files(self):
        """
        Clean up orphaned files older than 2 hours
        """
        cutoff_time = datetime.now() - timedelta(hours=2)
        cleaned_count = 0
        
        # Check tracked files
        with self.lock:
            orphaned_files = [
                path for path, info in self.active_uploads.items()
                if info['created_at'] < cutoff_time
            ]
        
        # Clean up orphaned tracked files
        for file_path in orphaned_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    cleaned_count += 1
                    logger.info(f"Cleaned up orphaned temp file: {file_path}")
                
                # Remove from tracking
                self.active_uploads.pop(file_path, None)
                
            except Exception as e:
                logger.error(f"Error cleaning up orphaned file {file_path}: {str(e)}")
        
        # Check for untracked files in temp directory
        try:
            for file_path in self.root_path.glob('*.zip'):
                if str(file_path) not in self.active_uploads:
                    # Check file age
                    file_time = datetime.fromtimestamp(file_path.stat().st_ctime)
                    if file_time < cutoff_time:
                        try:
                            file_path.unlink()
                            cleaned_count += 1
                            logger.info(f"Cleaned up untracked orphaned file: {file_path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up untracked file {file_path}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error scanning temp directory: {str(e)}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} orphaned SCORM temp files")
    
    def start_cleanup_monitor(self):
        """Start background thread to monitor and cleanup orphaned files"""
        def cleanup_monitor():
            while True:
                try:
                    self.cleanup_orphaned_files()
                    time.sleep(1800)  # Check every 30 minutes
                except Exception as e:
                    logger.error(f"Error in cleanup monitor: {str(e)}")
                    time.sleep(300)  # Wait 5 minutes before retrying
        
        cleanup_thread = threading.Thread(target=cleanup_monitor, daemon=True)
        cleanup_thread.start()
        logger.info("Started SCORM temp file cleanup monitor")
    
    def get_stats(self):
        """Get statistics about temporary files"""
        with self.lock:
            total_files = len(self.active_uploads)
            total_size = 0
            
            for info in self.active_uploads.values():
                if 'size' in info:
                    total_size += info['size']
            
            return {
                'active_files': total_files,
                'total_size_mb': total_size / (1024 * 1024),
                'temp_directory': str(self.root_path),
                'files': dict(self.active_uploads)
            }

# Global instance
temp_scorm_storage = TempSCORMStorage()
