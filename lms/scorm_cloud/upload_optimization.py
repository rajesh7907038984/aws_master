
import os
import tempfile
import shutil
from pathlib import Path

def optimize_large_file_upload(file_path, max_chunk_size=100*1024*1024):
    """Optimize large file upload by creating temporary chunks if needed"""
    
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"File size: {file_size_mb:.1f}MB")
    
    # For files larger than 500MB, we might want to optimize
    if file_size_mb > 500:
        print(f"Large file detected ({file_size_mb:.1f}MB) - applying optimizations")
        
        # Create a temporary directory for processing
        temp_dir = tempfile.mkdtemp(prefix='scorm_large_upload_')
        temp_file = os.path.join(temp_dir, os.path.basename(file_path))
        
        try:
            # Copy file to temp location for processing
            shutil.copy2(file_path, temp_file)
            print(f"Created temporary file: {temp_file}")
            
            # Return the temporary file path
            return temp_file, temp_dir
        except Exception as e:
            print(f"Error creating temporary file: {e}")
            return file_path, None
    else:
        print("File size is manageable - no optimization needed")
        return file_path, None

def cleanup_temp_files(temp_file, temp_dir):
    """Clean up temporary files after upload"""
    try:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Error cleaning up temporary files: {e}")
