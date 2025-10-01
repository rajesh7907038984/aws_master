"""
Enhanced Temporary File Manager for SCORM Uploads
Provides robust temporary file handling with automatic cleanup and monitoring.
"""

import os
import tempfile
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from django.conf import settings

logger = logging.getLogger(__name__)

class SCORMTempFileManager:
    """
    Enhanced temporary file manager for SCORM uploads with:
    - Automatic cleanup
    - Size monitoring
    - Thread-safe operations
    - Orphaned file detection
    """
    
    def __init__(self):
        self.temp_files = {}  # Track active temp files
        self.lock = threading.Lock()
        self.cleanup_thread = None
        self.start_cleanup_monitor()
    
    @contextmanager
    def create_temp_file(self, uploaded_file, prefix="scorm_", suffix=".zip"):
        """
        Context manager for creating and managing temporary files.
        
        Usage:
            with temp_manager.create_temp_file(uploaded_file) as temp_path:
                # Use temp_path for SCORM upload
                scorm_client.upload_package(temp_path, ...)
        """
        temp_file = None
        temp_path = None
        
        try:
            # Create temporary file with unique name
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                prefix=prefix, 
                suffix=suffix,
                dir=self.get_temp_directory()
            )
            temp_path = temp_file.name
            
            # Track the file
            with self.lock:
                self.temp_files[temp_path] = {
                    'created_at': datetime.now(),
                    'size': 0,
                    'status': 'creating'
                }
            
            logger.info(f"Creating temporary SCORM file: {temp_path}")
            
            # Write uploaded file content
            total_size = 0
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
                total_size += len(chunk)
            
            temp_file.close()
            
            # Update tracking info
            with self.lock:
                if temp_path in self.temp_files:
                    self.temp_files[temp_path].update({
                        'size': total_size,
                        'status': 'ready'
                    })
            
            logger.info(f"Temporary file ready: {temp_path} ({total_size/(1024*1024):.2f}MB)")
            
            yield temp_path
            
        except Exception as e:
            logger.error(f"Error creating temporary file: {str(e)}")
            raise
        finally:
            # Always cleanup
            self.cleanup_file(temp_path)
    
    def cleanup_file(self, file_path):
        """Safely remove a temporary file"""
        if not file_path:
            return
            
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Removed temporary file: {file_path}")
            
            # Remove from tracking
            with self.lock:
                self.temp_files.pop(file_path, None)
                
        except Exception as e:
            logger.error(f"Error removing temporary file {file_path}: {str(e)}")
    
    def get_temp_directory(self):
        """Get or create temporary directory for SCORM files"""
        temp_dir = os.path.join(tempfile.gettempdir(), 'lms_scorm')
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    
    def start_cleanup_monitor(self):
        """Start background thread to monitor and cleanup orphaned files"""
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            return
            
        def cleanup_monitor():
            while True:
                try:
                    self.cleanup_orphaned_files()
                    time.sleep(300)  # Check every 5 minutes
                except Exception as e:
                    logger.error(f"Error in cleanup monitor: {str(e)}")
                    time.sleep(60)  # Wait 1 minute before retrying
        
        self.cleanup_thread = threading.Thread(target=cleanup_monitor, daemon=True)
        self.cleanup_thread.start()
        logger.info("Started SCORM temp file cleanup monitor")
    
    def cleanup_orphaned_files(self):
        """Remove orphaned temporary files older than 1 hour"""
        cutoff_time = datetime.now() - timedelta(hours=1)
        temp_dir = self.get_temp_directory()
        
        if not os.path.exists(temp_dir):
            return
        
        orphaned_count = 0
        
        # Check tracked files
        with self.lock:
            orphaned_files = [
                path for path, info in self.temp_files.items()
                if info['created_at'] < cutoff_time
            ]
        
        # Remove orphaned tracked files
        for file_path in orphaned_files:
            self.cleanup_file(file_path)
            orphaned_count += 1
        
        # Check for untracked files in temp directory
        try:
            for filename in os.listdir(temp_dir):
                if filename.startswith('scorm_') and filename.endswith('.zip'):
                    file_path = os.path.join(temp_dir, filename)
                    if os.path.exists(file_path):
                        # Check file age
                        file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                        if file_time < cutoff_time:
                            try:
                                os.unlink(file_path)
                                orphaned_count += 1
                                logger.info(f"Removed orphaned temp file: {file_path}")
                            except Exception as e:
                                logger.error(f"Error removing orphaned file {file_path}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error scanning temp directory: {str(e)}")
        
        if orphaned_count > 0:
            logger.info(f"Cleaned up {orphaned_count} orphaned SCORM temp files")
    
    def get_stats(self):
        """Get statistics about temporary files"""
        with self.lock:
            total_files = len(self.temp_files)
            total_size = sum(info['size'] for info in self.temp_files.values())
            
            return {
                'active_files': total_files,
                'total_size_mb': total_size / (1024 * 1024),
                'temp_directory': self.get_temp_directory(),
                'files': dict(self.temp_files)
            }

# Global instance
temp_file_manager = SCORMTempFileManager()
