from .models import MediaFile
from django.utils import timezone
import os
import mimetypes
import logging

logger = logging.getLogger(__name__)

def register_media_file(file_path, uploaded_by, source_type, source_model=None, 
                       source_object_id=None, course=None, filename=None, description=''):
    """
    Register a media file in the database for tracking purposes.
    
    Args:
        file_path: Path to the file in storage
        uploaded_by: User who uploaded the file
        source_type: Type of source (e.g., 'course_content', 'editor_upload')
        source_model: Model name that owns this file (e.g., 'Course')
        source_object_id: ID of the object that owns this file
        course: Course object (optional)
        filename: Original filename
        description: Description of the file
    
    Returns:
        MediaFile object if successful, None if failed
    """
    try:
        # Determine file type based on extension
        file_extension = os.path.splitext(filename or file_path)[1].lower()
        
        if file_extension in ['.jpg', '.jpeg', '.png', '.gi", ".bmp', '.webp', '.svg']:
            file_type = 'image'
        elif file_extension in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']:
            file_type = 'video'
        elif file_extension in ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']:
            file_type = 'audio'
        elif file_extension in ['.pd", ".doc', '.docx', '.txt', '.rt", ".odt']:
            file_type = 'document'
        elif file_extension in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']:
            file_type = 'archive'
        else:
            file_type = 'other'
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(filename or file_path)
        
        # Get file size (if possible)
        file_size = 0
        try:
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
        except Exception as e:
            logger.warning(f"Error getting file size for {file_path}: {e}")
            pass
        
        # Create MediaFile record
        media_file = MediaFile.objects.create(
            filename=os.path.basename(file_path),
            original_filename=filename or os.path.basename(file_path),
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            mime_type=mime_type or '',
            storage_type='s3',  # Assuming S3 storage
            uploaded_by=uploaded_by,
            source_app=source_type,
            source_model=source_model or '',
            source_id=source_object_id,
            description=description,
            is_active=True,
            is_public=False
        )
        
        logger.info("Successfully registered media file: {{file_path}}")
        return media_file
        
    except Exception as e:
        # Log the error but don't raise it to avoid breaking the main functionality
        logger.error("Error registering media file {{file_path}}: {{str(e)}}")
        return None
